#!/usr/bin/env python3
"""Report local reverse-engineering route compatibility conservatively.

The default mode reads metadata only. ``--probe-executables`` explicitly opts
in to bounded background/version/import probes; those probes never connect an
agent bridge or open user geometry, but a third-party executable may perform
its own initialization. Unknown means unverified, not unsupported.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import signal
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python >=3.11 is required by the bundled CAD runtime.
    tomllib = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
COMPATIBILITY = ROOT / "compatibility.json"
BLENDER_MARKER = "PCRE_PREFLIGHT="


def run_bounded(
    command: list[str], timeout: float = 10, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str] | None:
    popen_options: dict[str, Any] = {}
    if os.name == "posix":
        popen_options["start_new_session"] = True
    elif os.name == "nt":  # pragma: no cover - exercised by Windows CI/users.
        popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            env=env,
            **popen_options,
        )
    except (FileNotFoundError, OSError):
        return None
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except OSError:
                pass
        else:  # pragma: no cover - best-effort fallback without a POSIX process group.
            try:
                process.terminate()
            except OSError:
                pass
        try:
            process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
            else:  # pragma: no cover - best-effort fallback without a POSIX process group.
                try:
                    process.kill()
                except OSError:
                    pass
            process.communicate()
        return None
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def resolve_executable(command: str | None, defaults: tuple[str, ...]) -> str | None:
    choices = (command,) if command else defaults
    for choice in choices:
        if not choice:
            continue
        if os.sep in choice or (os.altsep and os.altsep in choice) or Path(choice).is_absolute():
            candidate = Path(choice).expanduser()
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate.resolve())
            continue
        found = shutil.which(choice)
        if found:
            return found
    return None


def probe_python() -> dict[str, Any]:
    return {
        "status": "detected",
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "abi": sys.implementation.cache_tag,
    }


def probe_python_package(name: str, *, execute: bool = False) -> dict[str, Any]:
    if importlib.util.find_spec(name) is None:
        return {"status": "missing", "version": None}
    distributions = importlib.metadata.packages_distributions().get(name, [name])
    version = "unknown"
    for distribution in distributions:
        try:
            version = importlib.metadata.version(distribution)
            break
        except importlib.metadata.PackageNotFoundError:
            continue
    if not execute:
        return {
            "status": "present_unverified",
            "version": version,
            "runtime_verified": False,
            "probe": "metadata-only",
        }
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = run_bounded(
        [
            sys.executable,
            "-B",
            "-c",
            "import importlib,sys; importlib.import_module(sys.argv[1])",
            name,
        ],
        15,
        env=env,
    )
    verified = completed is not None and completed.returncode == 0
    return {
        "status": "detected" if verified else "present_unverified",
        "version": version,
        "runtime_verified": verified,
        "probe": "bounded-executable",
    }


def probe_blender(command: str | None = None, *, execute: bool = False) -> dict[str, Any]:
    executable = resolve_executable(command, ("blender",))
    if not executable:
        return {"status": "missing", "version": None, "python": None, "abi": None}
    if not execute:
        return {
            "status": "present_unverified",
            "version": None,
            "python": None,
            "abi": None,
            "probe": "metadata-only",
        }
    expression = (
        "import bpy,json,sys;print(" + repr(BLENDER_MARKER)
        + "+json.dumps({'version':bpy.app.version_string,'python':sys.version.split()[0],"
        "'abi':sys.implementation.cache_tag}))"
    )
    completed = run_bounded([executable, "--background", "--factory-startup", "--python-expr", expression], 20)
    if completed is None:
        return {"status": "unknown", "version": None, "python": None, "abi": None}
    output = completed.stdout + "\n" + completed.stderr
    for line in output.splitlines():
        if line.startswith(BLENDER_MARKER):
            try:
                payload = json.loads(line[len(BLENDER_MARKER):])
            except json.JSONDecodeError:
                break
            payload["status"] = "detected" if completed.returncode == 0 else "unknown"
            payload["probe"] = "bounded-executable"
            return payload
    version_run = run_bounded([executable, "--version"])
    version_match = re.search(r"Blender\s+([^\s]+)", version_run.stdout if version_run else "")
    return {
        "status": "present_unverified" if version_match else "unknown",
        "version": version_match.group(1) if version_match else None,
        "python": None,
        "abi": None,
        "probe": "bounded-executable",
    }


def blender_config_roots() -> list[Path]:
    roots: list[Path] = []
    if os.environ.get("XDG_CONFIG_HOME"):
        roots.append(Path(os.environ["XDG_CONFIG_HOME"]) / "blender")
    roots.append(Path.home() / ".config" / "blender")
    roots.append(Path.home() / "Library" / "Application Support" / "Blender")
    if os.environ.get("APPDATA"):
        roots.append(Path(os.environ["APPDATA"]) / "Blender Foundation" / "Blender")
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def extension_manifests(blender_version: str | None) -> list[tuple[Path, dict[str, Any]]]:
    if tomllib is None:
        return []
    requested_series = None
    match = re.match(r"^(\d+\.\d+)", blender_version or "")
    if match:
        requested_series = match.group(1)
    candidates: list[tuple[int, Path, dict[str, Any]]] = []
    for root in blender_config_roots():
        if not root.is_dir():
            continue
        for manifest in root.glob("*/extensions/*/*/blender_manifest.toml"):
            try:
                data = tomllib.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            try:
                series = manifest.relative_to(root).parts[0]
            except ValueError:
                series = ""
            if requested_series is not None and series != requested_series:
                continue
            candidates.append((0 if series == requested_series else 1, manifest, data))
    candidates.sort(key=lambda item: (item[0], str(item[1])))
    return [(path, data) for _, path, data in candidates]


def probe_extension(
    manifests: list[tuple[Path, dict[str, Any]]],
    *,
    identifiers: tuple[str, ...],
    blender_abi: str | None,
) -> dict[str, Any]:
    selected: tuple[Path, dict[str, Any]] | None = None
    for path, data in manifests:
        identity = re.sub(r"[^a-z0-9]+", " ", " ".join(
            str(data.get(key, "")) for key in ("id", "name")
        ).casefold()).strip()
        normalized_identifiers = [re.sub(r"[^a-z0-9]+", " ", item.casefold()).strip() for item in identifiers]
        if any(identifier in identity for identifier in normalized_identifiers):
            selected = (path, data)
            break
    if selected is None:
        return {"status": "missing", "version": None}
    path, data = selected
    result: dict[str, Any] = {
        # An installed manifest proves neither that an extension is enabled nor
        # that its runtime can load in the selected Blender process.
        "status": "present_unverified",
        "version": data.get("version"),
        "id": data.get("id"),
        "enabled": None,
        "runtime_verified": False,
    }
    wheels = data.get("wheels")
    wheel_abis = sorted({match.group(1) for wheel in wheels or []
                         if (match := re.search(r"-(cp\d+)-", str(wheel)))})
    if wheel_abis:
        result["wheel_abis"] = wheel_abis
    embedded_abi = None
    match = re.match(r"cpython-(\d+)", blender_abi or "")
    if match:
        embedded_abi = "cp" + match.group(1)
        result["embedded_abi"] = embedded_abi
    if embedded_abi and wheel_abis and embedded_abi not in wheel_abis:
        result["status"] = "incompatible"
        result["reason"] = f"no bundled solver wheel for {embedded_abi}"
    # Deliberately do not return the personal extension path.
    return result


def probe_cloudcompare(command: str | None = None, *, execute: bool = False) -> dict[str, Any]:
    executable = resolve_executable(command, ("CloudCompare", "cloudcompare"))
    if not executable:
        return {"status": "missing", "version": None}
    if not execute:
        return {"status": "present_unverified", "version": None, "probe": "metadata-only"}
    version: str | None = None
    completed = run_bounded([executable, "--version"], 5)
    output = (completed.stdout + "\n" + completed.stderr) if completed else ""
    match = re.search(r"CloudCompare\s+(?:v)?(\d+\.\d+(?:\.\d+)?)", output, re.I)
    if match:
        version = match.group(1)
    return {
        "status": "detected" if version else "present_unverified",
        "version": version,
        "probe": "bounded-executable",
    }


def probe_bridge_command(command: str | None, *, execute: bool = False) -> dict[str, Any]:
    found = resolve_executable(command, ("mcp-server-blender", "blender-mcp"))
    if not found:
        return {"status": "missing", "command": None, "version": None}
    if not execute:
        return {
            "status": "present_unverified",
            "command": Path(found).name,
            "version": None,
            "probe": "metadata-only",
        }
    completed = run_bounded([found, "--version"], 5)
    output = (completed.stdout + "\n" + completed.stderr) if completed else ""
    match = re.search(r"\b(\d+\.\d+(?:\.\d+)?)\b", output)
    version = match.group(1) if match else None
    return {
        "status": "detected" if version else "present_unverified",
        "command": Path(found).name,
        "version": version,
        "probe": "bounded-executable",
    }


def probe_cadgen(*, execute: bool = False) -> dict[str, Any]:
    package = ROOT / "skills" / "cad" / "scripts" / "packages" / "cadgen"
    pyproject = package / "pyproject.toml"
    source = package / "src"
    if not pyproject.is_file() or tomllib is None:
        return {"status": "missing", "version": None, "runtime_verified": False}
    try:
        version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, KeyError, ValueError):
        return {"status": "unknown", "version": None, "runtime_verified": False}
    if not execute:
        return {
            "status": "present_unverified",
            "version": version,
            "runtime_verified": False,
            "probe": "metadata-only",
            "reason": "vendored source is present; runtime imports were not requested",
        }
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(source) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    completed = run_bounded(
        [sys.executable, "-B", "-c", "import build123d, OCP, cadgen"], 15, env=env
    )
    verified = completed is not None and completed.returncode == 0
    return {
        "status": "detected" if verified else "present_unverified",
        "version": version,
        "runtime_verified": verified,
        "probe": "bounded-executable",
        "reason": None if verified else "vendored source is present but the bounded build123d/OCP import canary failed",
    }


def normalized_version(value: Any) -> str | None:
    match = re.search(r"\b(\d+\.\d+\.\d+)\b", str(value or ""))
    return match.group(1) if match else None


def version_equal(detected: Any, expected: Any) -> bool:
    detected_version = normalized_version(detected)
    expected_version = normalized_version(expected)
    return bool(detected_version and expected_version and detected_version == expected_version)


def observation_matches(
    name: str,
    detected: dict[str, Any],
    observation: dict[str, Any],
    detections: dict[str, dict[str, Any]],
) -> bool:
    if "version" in observation and not version_equal(detected.get("version"), observation["version"]):
        return False
    if "embedded_python" in observation and not version_equal(detected.get("python"), observation["embedded_python"]):
        return False
    if "embedded_python_abi" in observation and detected.get("abi") != observation["embedded_python_abi"]:
        return False
    if "abi" in observation and detected.get("abi") != observation["abi"]:
        return False
    dependencies = {
        "blender": ("blender", "version", version_equal),
        "blender_python": ("blender_python_abi", "version", version_equal),
        "blender_python_abi": ("blender_python_abi", "abi", lambda a, b: a == b),
        "host_python": ("host_python", "version", version_equal),
        "host_python_abi": ("host_python", "abi", lambda a, b: a == b),
        "cad_sketcher": ("cad_sketcher", "version", version_equal),
    }
    for field, (dependency, key, comparator) in dependencies.items():
        if field in observation and not comparator(detections.get(dependency, {}).get(key), observation[field]):
            return False
    # A tested Blender tuple is incomplete without embedded Python evidence.
    if name == "blender" and (not detected.get("python") or not detected.get("abi")):
        return False
    return True


def assess_components(
    detections: dict[str, dict[str, Any]], compatibility: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    assessed: dict[str, dict[str, Any]] = {}
    declarations = compatibility.get("components", {})
    for name, detected in detections.items():
        result = dict(detected)
        detection_status = str(detected.get("status", "unknown"))
        result["detection_status"] = detection_status
        if detection_status in {"missing", "incompatible", "unknown"}:
            result["status"] = detection_status
            assessed[name] = result
            continue
        declaration = declarations.get(name)
        if not isinstance(declaration, dict):
            result["status"] = "unknown"
            result["compatibility_reason"] = "component has no compatibility declaration"
            assessed[name] = result
            continue
        if declaration.get("status") == "unknown":
            result["status"] = "unknown"
            result["compatibility_reason"] = "component implementation/version is deployment-specific"
            assessed[name] = result
            continue
        incompatible = declaration.get("known_incompatible", [])
        if any(observation_matches(name, detected, item, detections) for item in incompatible):
            result["status"] = "incompatible"
            result["compatibility_reason"] = "detected tuple matches a known-incompatible observation"
            assessed[name] = result
            continue
        tested = declaration.get("tested", [])
        if any(observation_matches(name, detected, item, detections) for item in tested):
            if detection_status != "detected" or detected.get("runtime_verified") is False:
                result["status"] = "present_unverified"
                result["compatibility_reason"] = (
                    "version metadata matches, but enabled/runtime state was not verified"
                )
            else:
                result["status"] = "tested"
                result["compatibility_reason"] = "exact tested component tuple"
            assessed[name] = result
            continue
        probe_only = declaration.get("probe_only", [])
        if any(observation_matches(name, detected, item, detections) for item in probe_only):
            result["status"] = "present_unverified"
            result["compatibility_reason"] = "exact probe-only observation; route behavior is unverified"
            assessed[name] = result
            continue
        locked_version = declaration.get("locked_version")
        if locked_version and version_equal(detected.get("version"), locked_version):
            result["status"] = "tested" if detected.get("runtime_verified") else "present_unverified"
            result["compatibility_reason"] = (
                "locked source and runtime canary match" if detected.get("runtime_verified")
                else "locked source is present, but runtime dependencies are unverified"
            )
            assessed[name] = result
            continue
        result["status"] = "unknown"
        result["compatibility_reason"] = "detected implementation/version is outside compatibility.json"
        assessed[name] = result
    return assessed


def route_status(components: dict[str, dict[str, Any]], required: list[str]) -> str:
    if any(name not in components for name in required):
        return "unknown"
    states = [components[name]["status"] for name in required]
    if any(state == "incompatible" for state in states):
        return "blocked_incompatible"
    if any(state == "missing" for state in states):
        return "blocked_missing"
    if any(state == "unknown" for state in states):
        return "unknown"
    if any(state in {"present_unverified", "available_unverified"} for state in states):
        return "available_unverified"
    if all(state in {"available", "tested"} for state in states):
        return "available"
    return "unknown"


def strict_route_passes(status: str, *, allow_unverified: bool = False) -> bool:
    return status == "available" or (allow_unverified and status == "available_unverified")


def make_report(args: argparse.Namespace) -> dict[str, Any]:
    compatibility = json.loads(COMPATIBILITY.read_text(encoding="utf-8"))
    execute = bool(args.probe_executables)
    blender = probe_blender(args.blender, execute=execute)
    manifests = extension_manifests(blender.get("version"))
    host_python = probe_python()
    if blender.get("status") == "missing":
        blender_python = {"status": "missing", "version": None, "abi": None}
    elif blender.get("python") and blender.get("abi"):
        blender_python = {
            "status": "detected",
            "version": blender["python"],
            "abi": "cp" + blender["abi"].split("-", 1)[-1] if blender["abi"].startswith("cpython-") else blender["abi"],
        }
    else:
        blender_python = {"status": "unknown", "version": blender.get("python"), "abi": blender.get("abi")}
    detections = {
        "host_python": host_python,
        "blender": blender,
        "blender_python_abi": blender_python,
        "cad_sketcher": probe_extension(
            manifests, identifiers=("cad_sketcher", "cad sketcher"), blender_abi=blender.get("abi")
        ),
        "agent_bridge": probe_extension(
            manifests, identifiers=("agent bridge", "agent_bridge", "claude_blender"), blender_abi=blender.get("abi")
        ),
        "agent_bridge_command": probe_bridge_command(args.bridge_command, execute=execute),
        "open3d": probe_python_package("open3d", execute=execute),
        "numpy": probe_python_package("numpy", execute=execute),
        "scipy": probe_python_package("scipy", execute=execute),
        "trimesh": probe_python_package("trimesh", execute=execute),
        "cloudcompare": probe_cloudcompare(args.cloudcompare, execute=execute),
        "cadgen": probe_cadgen(execute=execute),
        "browser_occt": {"status": "unknown", "version": None},
        "bricscad": {"status": "unknown", "version": None},
        "autodesk_fusion": {"status": "unknown", "version": None},
    }
    components = assess_components(detections, compatibility)
    routes: dict[str, Any] = {}
    for name, route in compatibility["routes"].items():
        required = route.get("required_components", [])
        status = route_status(components, required)
        if status == "available" and route.get("tested") is not True:
            status = "available_unverified"
        routes[name] = {
            "status": status,
            "tested_route": route.get("tested") is True,
            "required_components": required,
            "unknowns": route.get("unknowns", []),
        }
    return {
        "schema_version": 1,
        "probe_mode": "bounded-executable" if execute else "metadata-only",
        "policy": (
            "Unknown means unverified, not unsupported. Metadata-only mode does not launch discovered tools. "
            "Bounded-executable mode is explicit and may trigger tool-specific initialization."
        ),
        "components": components,
        "routes": routes,
        "outside_scope": compatibility.get("outside_scope", []),
    }


def self_test() -> None:
    assert route_status({"a": {"status": "tested"}}, ["a"]) == "available"
    assert route_status({"a": {"status": "missing"}}, ["a"]) == "blocked_missing"
    assert route_status({"a": {"status": "incompatible"}}, ["a"]) == "blocked_incompatible"
    assert route_status({"a": {"status": "present_unverified"}}, ["a"]) == "available_unverified"
    assert route_status({"a": {"status": "unknown"}}, ["a"]) == "unknown"
    assert not strict_route_passes("unknown")
    assert not strict_route_passes("available_unverified")
    assert strict_route_passes("available_unverified", allow_unverified=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write the JSON report to this path")
    parser.add_argument("--strict-route", help="return nonzero unless this exact tested route is available")
    parser.add_argument("--allow-unverified", action="store_true",
                        help="with --strict-route, also accept a fully identified but probe-only route")
    parser.add_argument("--blender", help="explicit Blender executable")
    parser.add_argument("--cloudcompare", help="explicit CloudCompare executable")
    parser.add_argument("--bridge-command", help="explicit agent bridge command")
    parser.add_argument(
        "--probe-executables",
        action="store_true",
        help=(
            "explicitly launch bounded background/version/import probes; third-party tools may initialize "
            "host caches or configuration"
        ),
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("compatibility preflight self-test: ok")
        return 0
    report = make_report(args)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    if args.strict_route:
        route = report["routes"].get(args.strict_route)
        if route is None:
            print(f"unknown route: {args.strict_route}", file=sys.stderr)
            return 2
        return 0 if strict_route_passes(route["status"], allow_unverified=args.allow_unverified) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
