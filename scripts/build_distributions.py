#!/usr/bin/env python3
"""Build source-map-free plugin archives deterministically under a fixed builder."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "distribution.json"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def load_config() -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError("distribution.json schema_version must be 1")
    validate_config_paths(config)
    return config


def compression_settings(config: dict[str, Any]) -> tuple[int, int | None]:
    compression = config.get("reproducibility", {}).get("compression")
    if compression == "deflate-9":
        return zipfile.ZIP_DEFLATED, 9
    if compression == "stored":
        return zipfile.ZIP_STORED, None
    raise ValueError(f"unsupported distribution compression: {compression!r}")


def safe_config_path(value: Any, label: str, *, single_component: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty relative POSIX path")
    if "\\" in value or value.startswith(("/", "//")) or re_windows_absolute(value):
        raise ValueError(f"{label} must not be absolute or use backslashes: {value!r}")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError(f"{label} contains an unsafe path component: {value!r}")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise ValueError(f"{label} contains an unsafe path component: {value!r}")
    if single_component and len(parsed.parts) != 1:
        raise ValueError(f"{label} must be one safe path component: {value!r}")
    return parsed.as_posix()


def re_windows_absolute(value: str) -> bool:
    return len(value) >= 2 and value[0].isalpha() and value[1] == ":"


def validate_config_paths(config: dict[str, Any]) -> None:
    archive_root = safe_config_path(config.get("archive_root"), "archive_root", single_component=True)
    plugin_name, _ = plugin_identity()
    if archive_root != plugin_name:
        raise ValueError("archive_root must equal the plugin name")
    common = config.get("common_files")
    if not isinstance(common, list) or not common:
        raise ValueError("common_files must be a non-empty array")
    for index, relative in enumerate(common):
        safe_config_path(relative, f"common_files[{index}]")
    patterns = config.get("exclude_globs", [])
    if not isinstance(patterns, list):
        raise ValueError("exclude_globs must be an array")
    for index, pattern in enumerate(patterns):
        safe_config_path(pattern, f"exclude_globs[{index}]")
    for relative in common:
        if excluded(relative, patterns):
            raise ValueError(f"required common file is excluded by exclude_globs: {relative}")
    profiles = config.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("profiles must be a non-empty object")
    for profile, definition in profiles.items():
        safe_config_path(profile, f"profile name {profile!r}", single_component=True)
        if not isinstance(definition, dict):
            raise ValueError(f"profile {profile!r} must be an object")
        selection = definition.get("skills")
        if selection == "*":
            continue
        if not isinstance(selection, list) or not selection:
            raise ValueError(f"profile {profile!r} skills must be '*' or a non-empty array")
        for index, skill in enumerate(selection):
            safe_config_path(skill, f"profiles.{profile}.skills[{index}]", single_component=True)
        if len(selection) != len(set(selection)):
            raise ValueError(f"profile {profile!r} contains duplicate skills")


def reject_symlinks_and_special_files(directory: Path) -> None:
    if directory.is_symlink():
        raise ValueError(f"distribution input is a symlink: {directory.relative_to(ROOT)}")
    for current, directories, files in os.walk(directory, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *files]:
            candidate = current_path / name
            if candidate.is_symlink():
                raise ValueError(f"distribution input is a symlink: {candidate.relative_to(ROOT)}")
            mode = candidate.stat(follow_symlinks=False).st_mode
            if name in directories and not stat.S_ISDIR(mode):
                raise ValueError(f"distribution input is not a directory: {candidate.relative_to(ROOT)}")
            if name in files and not stat.S_ISREG(mode):
                raise ValueError(f"distribution input is not a regular file: {candidate.relative_to(ROOT)}")


def checked_input_file(relative: str) -> Path:
    safe = safe_config_path(relative, f"distribution input {relative!r}")
    path = ROOT.joinpath(*PurePosixPath(safe).parts)
    current = ROOT
    for component in PurePosixPath(safe).parts:
        current /= component
        if current.is_symlink():
            raise ValueError(f"distribution input traverses a symlink: {relative}")
    if not path.is_file() or not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
        raise FileNotFoundError(f"required distribution file is missing or not regular: {relative}")
    return path


def excluded(relative: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(relative, pattern) for pattern in patterns)


def selected_skills(config: dict[str, Any], profile: str) -> list[str]:
    selection = config["profiles"][profile]["skills"]
    available = sorted(
        path.name for path in (ROOT / "skills").iterdir()
        if not path.is_symlink() and path.is_dir() and (path / "SKILL.md").is_file()
    )
    if selection == "*":
        return available
    missing = sorted(set(selection) - set(available))
    if missing:
        raise ValueError(f"distribution profile {profile!r} names missing skills: {missing}")
    return list(selection)


def plugin_identity() -> tuple[str, str]:
    plugin = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    name = plugin.get("name")
    version = plugin.get("version")
    safe_config_path(name, "plugin name", single_component=True)
    if not re_full_slug(str(name)):
        raise ValueError(f"plugin name must be a lowercase kebab-case slug: {name!r}")
    if not isinstance(version, str) or not re_full_semver(version):
        raise ValueError(f"plugin version must be MAJOR.MINOR.PATCH: {version!r}")
    return name, version


def re_full_slug(value: str) -> bool:
    import re
    return re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) is not None


def re_full_semver(value: str) -> bool:
    import re
    return re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value) is not None


def collect_files(config: dict[str, Any], profile: str) -> list[Path]:
    patterns = list(config.get("exclude_globs", []))
    candidates: set[Path] = set()
    for relative in config["common_files"]:
        candidates.add(checked_input_file(relative))
    reject_symlinks_and_special_files(ROOT / "skills")
    for skill in selected_skills(config, profile):
        skill_root = ROOT / "skills" / skill
        for path in skill_root.rglob("*"):
            if path.is_file():
                candidates.add(path)
    files = []
    for path in candidates:
        relative = path.relative_to(ROOT).as_posix()
        if not excluded(relative, patterns):
            files.append(path)
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def archive_manifest(
    config: dict[str, Any], profile: str, payload: list[tuple[str, bytes, bool]]
) -> bytes:
    plugin_name, plugin_version = plugin_identity()
    records = [
        {
            "path": relative,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for relative, content, _ in sorted(payload)
    ]
    manifest = {
        "schema_version": 1,
        "plugin": plugin_name,
        "version": plugin_version,
        "profile": profile,
        "description": config["profiles"][profile]["description"],
        "skills": selected_skills(config, profile),
        "source_maps_included": False,
        "reproducibility": config["reproducibility"],
        "files": records,
    }
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def distribution_notice(config: dict[str, Any], profile: str) -> bytes:
    selected = selected_skills(config, profile)
    lines = [
        "# Distribution profile",
        "",
        f"Profile: `{profile}`",
        "",
        config["profiles"][profile]["description"],
        "",
        "Bundled skills: " + ", ".join(f"`{name}`" for name in selected) + ".",
        "",
        "Source maps are excluded from release archives only; the authoritative source tree remains unchanged.",
        "",
        "`vendor-lock.json` records provenance for the authoritative full source import, including files or skills omitted by this profile. `DISTRIBUTION-MANIFEST.json` records every non-manifest payload entry in this archive; release-level `SHA256SUMS` covers the complete ZIP.",
    ]
    if profile == "core":
        lines.extend([
            "",
            "Use the `full` archive or the normal repository installation when a manufacturing, printing, part-catalog, implicit-CAD, or robotics companion skill is required.",
        ])
    return ("\n".join(lines) + "\n").encode("utf-8")


def distribution_readme(config: dict[str, Any], profile: str) -> bytes:
    plugin_name, plugin_version = plugin_identity()
    selected = selected_skills(config, profile)
    lines = [
        f"# {plugin_name}",
        "",
        f"Release `{plugin_version}`, `{profile}` distribution.",
        "",
        config["profiles"][profile]["description"],
        "",
        "Bundled skills: " + ", ".join(f"`{name}`" for name in selected) + ".",
        "",
        "Install this extracted directory as a plugin, then start a new agent session.",
        "The normal repository installation remains the authoritative full source distribution.",
        "",
        "Run the included read-only host probe when checking local tool compatibility:",
        "",
        "```bash",
        "python3 scripts/compatibility_preflight.py",
        "```",
        "",
        "`DISTRIBUTION-MANIFEST.json` records the size and SHA-256 of every non-manifest payload entry.",
        "The release-level `SHA256SUMS` file covers the complete archive, including the manifest and generated distribution documentation.",
    ]
    if profile == "core":
        lines.extend([
            "",
            "Use the `full` archive for the optional manufacturing, printing, catalog, implicit-CAD, and robotics companion skills.",
        ])
    return ("\n".join(lines) + "\n").encode("utf-8")


def zip_info(name: str, executable: bool = False, compression: int = zipfile.ZIP_DEFLATED) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
    info.compress_type = compression
    info.create_system = 3
    mode = stat.S_IFREG | (0o755 if executable else 0o644)
    info.external_attr = mode << 16
    info.flag_bits |= 0x800  # UTF-8 names.
    return info


def build_profile(output_dir: Path, profile: str) -> Path:
    config = load_config()
    if profile not in config["profiles"]:
        raise ValueError(f"unknown distribution profile: {profile}")
    files = collect_files(config, profile)
    plugin_name, plugin_version = plugin_identity()
    archive = output_dir / f"{plugin_name}-{plugin_version}-{profile}.zip"
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = config["archive_root"].rstrip("/") + "/"
    compression, compresslevel = compression_settings(config)
    payload: list[tuple[str, bytes, bool]] = []
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        payload.append((relative, path.read_bytes(), bool(path.stat().st_mode & 0o111)))
    payload.extend([
        ("DISTRIBUTION-NOTICE.md", distribution_notice(config, profile), False),
        ("README.md", distribution_readme(config, profile), False),
    ])
    entries = [(prefix + relative, content, executable) for relative, content, executable in payload]
    entries.append((
        prefix + "DISTRIBUTION-MANIFEST.json",
        archive_manifest(config, profile, payload),
        False,
    ))
    with zipfile.ZipFile(archive, "w", compression=compression, compresslevel=compresslevel) as bundle:
        for name, content, executable in sorted(entries):
            bundle.writestr(zip_info(name, executable, compression), content, compresslevel=compresslevel)
    return archive


def verify_archive(path: Path, profile: str) -> None:
    config = load_config()
    prefix = config["archive_root"].rstrip("/") + "/"
    expected_compression, _ = compression_settings(config)
    with zipfile.ZipFile(path) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)):
            raise ValueError(f"archive contains duplicate entries: {path}")
        if names != sorted(names):
            raise ValueError(f"archive entries are not sorted: {path}")
        for info in bundle.infolist():
            name = info.filename
            parsed = PurePosixPath(name)
            if (name.startswith(("/", "//")) or "\\" in name or parsed.is_absolute()
                    or any(part in {"", ".", ".."} for part in parsed.parts)
                    or not name.startswith(prefix)):
                raise ValueError(f"unsafe archive entry {name!r} in {path}")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_IFMT(mode) == stat.S_IFLNK:
                raise ValueError(f"archive contains a symlink entry {name!r}")
            if info.compress_type != expected_compression:
                raise ValueError(f"archive entry {name!r} does not use configured compression")
        if any(name.casefold().endswith(".map") for name in names):
            raise ValueError(f"source map leaked into {path}")
        manifest_name = prefix + "DISTRIBUTION-MANIFEST.json"
        notice_name = prefix + "DISTRIBUTION-NOTICE.md"
        readme_name = prefix + "README.md"
        if manifest_name not in names or notice_name not in names or readme_name not in names:
            raise ValueError(f"distribution manifest missing from {path}")
        manifest = json.loads(bundle.read(manifest_name))
        if not isinstance(manifest, dict):
            raise ValueError(f"distribution manifest must be an object in {path}")
        plugin_name, plugin_version = plugin_identity()
        expected_metadata = {
            "schema_version": 1,
            "plugin": plugin_name,
            "version": plugin_version,
            "profile": profile,
            "description": config["profiles"][profile]["description"],
            "skills": selected_skills(config, profile),
            "source_maps_included": False,
            "reproducibility": config["reproducibility"],
        }
        actual_metadata = {key: manifest.get(key) for key in expected_metadata}
        if actual_metadata != expected_metadata:
            raise ValueError(
                f"distribution manifest metadata mismatch in {path}: "
                f"expected={expected_metadata!r}, actual={actual_metadata!r}"
            )
        expected_keys = set(expected_metadata) | {"files"}
        if set(manifest) != expected_keys:
            raise ValueError(f"distribution manifest has unexpected top-level fields in {path}")
        records = manifest.get("files")
        if not isinstance(records, list):
            raise ValueError(f"distribution manifest files must be an array in {path}")
        if any(not isinstance(record, dict) or not isinstance(record.get("path"), str) for record in records):
            raise ValueError(f"distribution manifest has malformed or duplicate paths in {path}")
        record_paths = [record["path"] for record in records]
        if len(record_paths) != len(set(record_paths)) or record_paths != sorted(record_paths):
            raise ValueError(f"distribution manifest has malformed, duplicate, or unsorted paths in {path}")
        expected_content = {
            source.relative_to(ROOT).as_posix(): source.read_bytes()
            for source in collect_files(config, profile)
        }
        expected_content["DISTRIBUTION-NOTICE.md"] = distribution_notice(config, profile)
        expected_content["README.md"] = distribution_readme(config, profile)
        if set(record_paths) != set(expected_content):
            extra = sorted(set(record_paths) - set(expected_content))
            missing = sorted(set(expected_content) - set(record_paths))
            raise ValueError(f"distribution manifest differs from expected payload: extra={extra}, missing={missing}")
        expected_payload_names: set[str] = set()
        for record in records:
            if set(record) != {"path", "bytes", "sha256"}:
                raise ValueError(f"distribution manifest record has unexpected fields in {path}")
            relative = safe_config_path(record["path"], "distribution manifest path")
            entry_name = prefix + relative
            expected_payload_names.add(entry_name)
            if entry_name not in names:
                raise ValueError(f"manifest entry is absent from archive: {relative}")
            content = bundle.read(entry_name)
            byte_count = record.get("bytes")
            if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
                raise ValueError(f"manifest byte count is malformed for {relative}")
            digest = record.get("sha256")
            if not isinstance(digest, str) or re_full_sha256(digest) is False:
                raise ValueError(f"manifest SHA-256 is malformed for {relative}")
            if byte_count != len(content):
                raise ValueError(f"manifest byte count mismatch for {relative}")
            if digest != hashlib.sha256(content).hexdigest():
                raise ValueError(f"manifest SHA-256 mismatch for {relative}")
            if content != expected_content[relative]:
                raise ValueError(f"archive entry differs from repository payload: {relative}")
        actual_payload_names = set(names) - {manifest_name}
        if actual_payload_names != expected_payload_names:
            extra = sorted(actual_payload_names - expected_payload_names)
            missing = sorted(expected_payload_names - actual_payload_names)
            raise ValueError(f"archive payload differs from manifest: extra={extra}, missing={missing}")
        expected_skills = set(selected_skills(config, profile))
        actual_skills = {name[len(prefix + 'skills/'):].split('/', 1)[0]
                         for name in names if name.startswith(prefix + "skills/")}
        if actual_skills != expected_skills:
            raise ValueError(f"archive skill set mismatch: expected {sorted(expected_skills)}, got {sorted(actual_skills)}")


def re_full_sha256(value: str) -> bool:
    import re
    return re.fullmatch(r"[0-9a-f]{64}", value) is not None


def deterministic_self_check(profiles: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="pc-re-dist-a-") as first, tempfile.TemporaryDirectory(
        prefix="pc-re-dist-b-"
    ) as second:
        for profile in profiles:
            a = build_profile(Path(first), profile)
            b = build_profile(Path(second), profile)
            verify_archive(a, profile)
            verify_archive(b, profile)
            if a.read_bytes() != b.read_bytes():
                raise ValueError(f"{profile} distribution is not byte-for-byte deterministic")


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--profile", action="append", choices=sorted(config["profiles"]),
                        help="build only this profile; may be repeated")
    parser.add_argument("--check", action="store_true", help="build twice in temporary directories and compare bytes")
    args = parser.parse_args(argv)
    profiles = args.profile or sorted(config["profiles"])
    if args.check:
        deterministic_self_check(profiles)
        print("distribution determinism: ok")
        return 0
    built: list[Path] = []
    for profile in profiles:
        archive = build_profile(args.output_dir, profile)
        verify_archive(archive, profile)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        print(f"{archive} sha256={digest}")
        built.append(archive)
    checksums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in sorted(built)
    )
    (args.output_dir / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"distribution build failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
