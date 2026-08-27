#!/usr/bin/env python3
"""Bump both plugin manifests from commits since the latest release tag.

The complete commit message is evaluated, not only its subject, so a
Conventional Commits ``BREAKING CHANGE:`` footer cannot be missed.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = (ROOT / "plugin.json", ROOT / ".codex-plugin" / "plugin.json")
SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
RELEASE_TAG = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def current_version() -> str:
    versions = [json.loads(path.read_text(encoding="utf-8")).get("version") for path in MANIFESTS]
    if (
        not all(isinstance(version, str) for version in versions)
        or len(set(versions)) != 1
        or SEMVER.fullmatch(versions[0]) is None
    ):
        raise ValueError(f"release manifests must contain the same plain semantic version: {versions!r}")
    return versions[0]


def release_baseline(version: str) -> str | None:
    """Return the highest reachable exact release tag and reject version skew."""

    candidates: list[tuple[tuple[int, int, int], str]] = []
    for tag in git("tag", "--merged", "HEAD", "--list").splitlines():
        match = RELEASE_TAG.fullmatch(tag.strip())
        if match:
            candidates.append((tuple(int(part) for part in match.groups()), tag.strip()))
    if not candidates:
        return None
    _, tag = max(candidates)
    tag_version = tag[1:]
    if tag_version != version:
        raise ValueError(
            f"manifest version {version} does not match latest reachable release tag {tag}; "
            "refusing to over-bump or skip commits"
        )
    return tag


def commits_since_last_tag(version: str | None = None) -> list[str]:
    version = version or current_version()
    baseline = release_baseline(version)
    revision_range = f"{baseline}..HEAD" if baseline else "HEAD"
    # A NUL separator is unambiguous even when bodies contain blank lines or
    # paragraph breaks. ``git()`` trims the final separator only.
    output = git("log", "--format=%B%x00", revision_range)
    return [message.strip() for message in output.split("\x00") if message.strip()]


def bump_level(messages: list[str]) -> str:
    headers = [message.splitlines()[0].strip() for message in messages if message.strip()]
    breaking_footer = re.compile(r"(?m)^BREAKING(?: CHANGE|-CHANGE):(?:[ \t].*)?$")
    breaking_header = re.compile(r"^[A-Za-z][A-Za-z0-9-]*(?:\([^\r\n)]+\))?!:")
    feature_header = re.compile(r"^feat(?:\([^\r\n)]+\))?:")

    if any(breaking_footer.search(message) for message in messages) or any(
        breaking_header.match(header) for header in headers
    ):
        return "major"
    if any(feature_header.match(header) or "[minor]" in header for header in headers):
        return "minor"
    return "patch"


def bumped(version: str, level: str) -> str:
    if SEMVER.fullmatch(version) is None:
        raise ValueError(f"version must be plain MAJOR.MINOR.PATCH: {version!r}")
    if level not in {"major", "minor", "patch"}:
        raise ValueError(f"unknown bump level: {level!r}")
    major, minor, patch = (int(part) for part in version.split("."))
    if level == "major":
        major, minor, patch = major + 1, 0, 0
    elif level == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


def self_test() -> None:
    assert bump_level(["docs: clarify install"]) == "patch"
    assert bump_level(["Merge pull request #1", "feat: add workflow"]) == "minor"
    assert bump_level(["feat(router): add browser route"]) == "minor"
    assert bump_level(["fix!: change the contract"]) == "major"
    assert bump_level(["feat(router)!: change route precedence"]) == "major"
    assert bump_level(["refactor(router)!: replace the dispatcher"]) == "major"
    assert bump_level(["docs!: remove supported instructions"]) == "major"
    assert bump_level(["fix: retain compatibility\n\nBREAKING CHANGE: remove v1 fields"]) == "major"
    assert bump_level(["fix: retain compatibility\n\nBREAKING-CHANGE: remove v1 fields"]) == "major"
    assert bump_level(["docs: explain the words BREAKING CHANGE without a footer"]) == "patch"
    assert bump_level(["feature: this is not a conventional feat header"]) == "patch"
    assert bumped("1.2.3", "patch") == "1.2.4"
    assert bumped("1.2.3", "minor") == "1.3.0"
    assert bumped("1.2.3", "major") == "2.0.0"


def main() -> int:
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        print("release self-test: ok")
        return 0

    version = current_version()
    messages = commits_since_last_tag(version)
    if not messages:
        print(version)
        return 0

    new_version = bumped(version, bump_level(messages))
    for manifest in MANIFESTS:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["version"] = new_version
        manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(new_version)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"release failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
