#!/usr/bin/env python3
"""Bump both plugin manifests from commits since the latest release tag."""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = (ROOT / "plugin.json", ROOT / ".codex-plugin" / "plugin.json")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def current_version() -> str:
    return json.loads(MANIFESTS[0].read_text(encoding="utf-8"))["version"]


def commits_since_last_tag() -> list[str]:
    try:
        revision_range = f"{git('describe', '--tags', '--abbrev=0')}..HEAD"
    except subprocess.CalledProcessError:
        revision_range = "HEAD"
    return [line for line in git("log", "--format=%s", revision_range).splitlines() if line.strip()]


def bump_level(subjects: list[str]) -> str:
    if any("BREAKING CHANGE" in subject or re.match(r"^(feat|fix)!", subject) for subject in subjects):
        return "major"
    if any(subject.startswith("feat") or "[minor]" in subject for subject in subjects):
        return "minor"
    return "patch"


def bumped(version: str, level: str) -> str:
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
    assert bump_level(["fix!: change the contract"]) == "major"
    assert bumped("1.2.3", "patch") == "1.2.4"
    assert bumped("1.2.3", "minor") == "1.3.0"
    assert bumped("1.2.3", "major") == "2.0.0"


def main() -> int:
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        print("release self-test: ok")
        return 0

    subjects = commits_since_last_tag()
    version = current_version()
    if not subjects:
        print(version)
        return 0

    new_version = bumped(version, bump_level(subjects))
    for manifest in MANIFESTS:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["version"] = new_version
        manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(new_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
