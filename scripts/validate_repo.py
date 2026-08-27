#!/usr/bin/env python3
"""Deterministic, dependency-free repository quality gate.

This command deliberately uses only the Python standard library so release
correctness does not depend on a locally installed Plugin Doctor or on network
availability. It validates package metadata, skill discovery contracts,
relative documentation links, deterministic routing fixtures, the point-cloud
feature contract, vendored-source integrity, and privacy canaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATHS = (
    Path("plugin.json"),
    Path(".codex-plugin/plugin.json"),
    Path(".agents/plugins/marketplace.json"),
)
POINT_SKILL = ROOT / "skills" / "point-cloud-reverse-engineering"
POINT_SCRIPTS = POINT_SKILL / "scripts"
if str(POINT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(POINT_SCRIPTS))

from pcre_tools.schema_subset import validate_instance as _validate_schema_subset  # noqa: E402

FEATURE_SCHEMA = POINT_SKILL / "assets" / "feature-contract.schema.json"
FEATURE_EXAMPLES = POINT_SKILL / "assets" / "contracts"
FEATURE_VALIDATOR = POINT_SKILL / "scripts" / "validate_feature_contract.py"
ROUTER_FIXTURES = ROOT / "tests" / "fixtures" / "router_cases.json"
ROUTER_CONTRACT = ROOT / "tests" / "router_contract.json"
VENDOR_LOCK = ROOT / "vendor-lock.json"
ROUTE_LABELS = {
    "linux-open-source": "Linux open source runtime",
    "stack-selection": "Stack execution",
    "operate": "Change",
    "read-only": "Read only inquiry",
}


class ValidationFailure(Exception):
    """One or more repository invariants failed."""


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.checks: list[str] = []

    def check(self, condition: bool, message: str) -> None:
        if not condition:
            self.errors.append(message)

    def ran(self, name: str) -> None:
        self.checks.append(name)


def load_json(path: Path, report: Report) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        report.errors.append(f"missing required JSON file: {path.relative_to(ROOT)}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        report.errors.append(f"invalid JSON in {path.relative_to(ROOT)}: {exc}")
    return None


def check_manifests(report: Report) -> None:
    plugin, codex, marketplace = [load_json(ROOT / path, report) for path in MANIFEST_PATHS]
    if not all(isinstance(value, dict) for value in (plugin, codex, marketplace)):
        return

    semver = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
    names = {plugin.get("name"), codex.get("name"), marketplace.get("name")}
    report.check(len(names) == 1 and None not in names, "all three manifests must use one plugin name")
    report.check(plugin.get("$schema") == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                 "plugin.json must declare the Agent Plugins 1.0.0 schema")
    report.check(plugin.get("license") == "MIT" and codex.get("license") == "MIT",
                 "plugin manifests must retain the MIT licence declaration")
    report.check(isinstance(plugin.get("description"), str) and bool(plugin["description"].strip()),
                 "plugin.json requires a non-empty description")
    report.check(isinstance(codex.get("description"), str) and bool(codex["description"].strip()),
                 ".codex-plugin/plugin.json requires a non-empty description")
    versions = [plugin.get("version"), codex.get("version")]
    report.check(versions[0] == versions[1], "version-bearing manifests must have equal versions")
    report.check(all(isinstance(version, str) and semver.fullmatch(version) for version in versions),
                 "manifest versions must be plain MAJOR.MINOR.PATCH values")
    report.check(codex.get("skills") == "./skills/", ".codex-plugin manifest must expose ./skills/")
    plugins = marketplace.get("plugins")
    report.check(isinstance(plugins, list) and len(plugins) == 1,
                 "marketplace manifest must contain exactly one plugin entry")
    if isinstance(plugins, list) and len(plugins) == 1 and isinstance(plugins[0], dict):
        entry = plugins[0]
        report.check(entry.get("name") == plugin.get("name"), "marketplace plugin name must match plugin.json")
        source = entry.get("source")
        report.check(source == {"source": "local", "path": "./"},
                     "marketplace source must remain the repository-local plugin root")
    report.ran("manifests")


def frontmatter_fields(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("frontmatter must start on the first line")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError("frontmatter is not closed") from exc
    fields: dict[str, str] = {}
    for number, line in enumerate(lines[1:end], 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) or ":" not in line:
            raise ValueError(f"unsupported multiline or malformed field at line {number}")
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"\'')
    return fields


def check_skill_frontmatter(report: Report) -> None:
    skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
    report.check(bool(skills), "at least one skills/*/SKILL.md is required")
    names: set[str] = set()
    for path in skills:
        label = path.relative_to(ROOT).as_posix()
        try:
            fields = frontmatter_fields(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            report.errors.append(f"{label}: {exc}")
            continue
        name = fields.get("name", "")
        description = fields.get("description", "")
        report.check(name == path.parent.name, f"{label}: name must equal directory name {path.parent.name!r}")
        report.check(bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)),
                     f"{label}: name must be lowercase kebab-case")
        report.check(name not in names, f"{label}: duplicate skill name {name!r}")
        report.check(1 <= len(description) <= 1024, f"{label}: description must be 1..1024 characters")
        names.add(name)
    report.ran(f"skill frontmatter ({len(skills)} skills)")


INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def local_link_target(raw: str) -> str | None:
    raw = raw.strip()
    if raw.startswith("<") and ">" in raw:
        raw = raw[1:raw.index(">")]
    else:
        # Markdown titles are separated from destinations by whitespace.
        raw = raw.split(maxsplit=1)[0]
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc or raw.startswith("#"):
        return None
    return unquote(parsed.path)


def check_relative_markdown_links(report: Report) -> None:
    checked = 0
    for path in sorted(ROOT.rglob("*.md")):
        if any(part in {".git", "dist"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            report.errors.append(f"Markdown is not UTF-8: {path.relative_to(ROOT)}")
            continue
        for match in INLINE_LINK.finditer(text):
            target = local_link_target(match.group(1))
            if not target:
                continue
            checked += 1
            destination = (path.parent / target).resolve()
            try:
                destination.relative_to(ROOT.resolve())
            except ValueError:
                report.errors.append(
                    f"{path.relative_to(ROOT)}: relative link escapes repository: {match.group(1)!r}"
                )
                continue
            report.check(destination.exists(),
                         f"{path.relative_to(ROOT)}: broken relative link {match.group(1)!r}")
    report.ran(f"relative Markdown links ({checked} links)")


def normalized_words(value: str) -> tuple[str, set[str]]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    words = re.findall(r"[a-z0-9]+", normalized)
    return " " + " ".join(words) + " ", set(words)


def classify_request(request: str, rules: list[dict[str, Any]], default: str | None) -> str | None:
    phrase_text, words = normalized_words(request)
    for rule in rules:
        terms = rule.get("any_terms", [])
        phrases = rule.get("any_phrases", [])
        if any(str(term).casefold() in words for term in terms) or any(
            normalized_words(str(phrase))[0] in phrase_text for phrase in phrases
        ):
            return rule["value"]
    return default


def _rule_matches(phrase_text: str, words: set[str], rule: dict[str, Any]) -> bool:
    return any(str(term).casefold() in words for term in rule.get("any_terms", [])) or any(
        normalized_words(str(phrase))[0] in phrase_text for phrase in rule.get("any_phrases", [])
    )


def classify_router_request(request: str, contract: dict[str, Any]) -> dict[str, str]:
    """Apply the same read-only-first intent grammar used by Plugin Doctor.

    Route declaration order remains human-readable and Doctor-compatible: the
    first rule is the non-mutating base and later rules are effectful routes.
    Read-only constraints and explanatory questions gate mutation before the
    effectful routes are considered; a direct or mixed execution request then
    uses the first matching effectful route.
    """

    route_rules = contract["route_rules"]
    read_only = route_rules[0]
    effectful = route_rules[1:]
    intent = contract["intent_rules"]
    phrase_text, words = normalized_words(request)
    normalized = unicodedata.normalize("NFKC", request).casefold()
    tokenized_sentences = [
        re.findall(r"[a-z0-9]+", sentence)
        for sentence in re.split(r"[.!?\n;]", normalized)
    ]
    tokenized_sentences = [tokens for tokens in tokenized_sentences if tokens]

    explicit_read_only = any(
        normalized_words(str(phrase))[0] in phrase_text
        for phrase in intent["explicit_read_only_phrases"]
    )
    if explicit_read_only:
        return {"route": read_only["value"], "mutation": "none"}

    question_words = set(intent["question_words"])
    advisory_auxiliaries = set(intent["advisory_auxiliaries"])
    advisory_subjects = set(intent["advisory_subjects"])
    direct_auxiliaries = set(intent["direct_request_auxiliaries"])
    determiners = set(intent["determiners"])
    effectful_terms = set().union(*(set(rule.get("any_terms", [])) for rule in effectful))

    content_question = any(tokens[0] in question_words for tokens in tokenized_sentences)
    advisory_question = any(
        len(tokens) > 1 and tokens[0] in advisory_auxiliaries and tokens[1] in advisory_subjects
        for tokens in tokenized_sentences
    )
    polite_direct = any(
        first in direct_auxiliaries and second == "you"
        for tokens in tokenized_sentences
        for first, second in zip(tokens, tokens[1:])
    )
    imperative_change = any(tokens[0] in effectful_terms for tokens in tokenized_sentences)

    change_candidates: set[str] = set()
    for tokens in tokenized_sentences:
        for index, token in enumerate(tokens):
            if token in effectful_terms and not (index and tokens[index - 1] in determiners):
                change_candidates.add(token)

    if not polite_direct and (content_question or advisory_question) and not imperative_change:
        return {"route": read_only["value"], "mutation": "none"}

    investigation = _rule_matches(phrase_text, words, read_only)
    for rule in effectful:
        terms_match = bool(change_candidates & set(rule.get("any_terms", [])))
        phrases_match = any(
            normalized_words(str(phrase))[0] in phrase_text
            for phrase in rule.get("any_phrases", [])
        )
        if terms_match or phrases_match:
            return {"route": rule["value"], "mutation": "scoped"}
    if investigation:
        return {"route": read_only["value"], "mutation": "none"}
    return {"route": contract.get("route_default", "fallback"), "mutation": "none"}


def skill_route_labels(text: str) -> list[str]:
    match = re.search(r"(?ms)^## Routes\s*$\n(.*?)(?=^## |\Z)", text)
    if not match:
        return []
    return re.findall(r"(?m)^- Select \*\*([^*]+)\*\*", match.group(1))


def skill_route_vocabulary(text: str) -> dict[str, dict[str, set[str]]]:
    match = re.search(r"(?ms)^## Routes\s*$\n(.*?)(?=^## |\Z)", text)
    if not match:
        return {}
    vocabulary: dict[str, dict[str, set[str]]] = {}
    for line_match in re.finditer(r"(?m)^- Select \*\*([^*]+)\*\* for (.*?)\. Read ", match.group(1)):
        label, clause = line_match.groups()
        terms: set[str] = set()
        phrases: set[str] = set()
        for token in re.findall(r"[a-z]+(?:-[a-z]+)*", clause.casefold()):
            if token in {"and", "or"}:
                continue
            if "-" in token:
                phrases.add(token.replace("-", " "))
            else:
                terms.add(token)
        vocabulary[label] = {"terms": terms, "phrases": phrases}
    return vocabulary


def check_router_fixtures(report: Report) -> None:
    fixtures = load_json(ROUTER_FIXTURES, report)
    contract = load_json(ROUTER_CONTRACT, report)
    if not isinstance(fixtures, list) or not isinstance(contract, dict):
        return
    route_rules = contract.get("route_rules")
    mutation_rules = contract.get("mutation_rules")
    if not isinstance(route_rules, list) or not isinstance(mutation_rules, list):
        report.errors.append("tests/router_contract.json must define route_rules and mutation_rules arrays")
        return
    intent_rules = contract.get("intent_rules")
    required_intent_lists = {
        "explicit_read_only_phrases",
        "question_words",
        "advisory_auxiliaries",
        "advisory_subjects",
        "direct_request_auxiliaries",
        "determiners",
    }
    report.check(bool(route_rules) and route_rules[0].get("value") == "read-only",
                 "the first route rule must be the Plugin Doctor read-only base")
    report.check(
        isinstance(intent_rules, dict)
        and required_intent_lists <= set(intent_rules)
        and all(
            isinstance(intent_rules.get(key), list)
            and bool(intent_rules[key])
            and all(isinstance(value, str) and value for value in intent_rules[key])
            for key in required_intent_lists
        ),
        "tests/router_contract.json must define every non-empty intent_rules vocabulary list",
    )
    if not route_rules or route_rules[0].get("value") != "read-only" or not isinstance(intent_rules, dict):
        return
    known_routes = {rule.get("value") for rule in route_rules if isinstance(rule, dict)}
    known_routes.add(contract.get("route_default"))
    known_mutations = {"none", "scoped"}
    expected_labels = [ROUTE_LABELS.get(rule.get("value"), "") for rule in route_rules if isinstance(rule, dict)]
    skill_text = (POINT_SKILL / "SKILL.md").read_text(encoding="utf-8")
    actual_labels = skill_route_labels(skill_text)
    report.check(
        actual_labels == expected_labels,
        f"SKILL.md route bullet order differs from router contract: expected={expected_labels}, actual={actual_labels}",
    )
    skill_vocabulary = skill_route_vocabulary(skill_text)
    for rule in route_rules:
        route = rule.get("value")
        label = ROUTE_LABELS.get(route, "")
        actual = skill_vocabulary.get(label, {"terms": set(), "phrases": set()})
        expected = {
            "terms": set(rule.get("any_terms", [])),
            "phrases": set(rule.get("any_phrases", [])),
        }
        report.check(actual == expected, f"SKILL.md vocabulary differs from router contract for {route}: expected={expected}, actual={actual}")
    effectful_terms = set().union(*(
        set(rule.get("any_terms", [])) for rule in route_rules if rule.get("value") != "read-only"
    ))
    scoped_terms = set().union(*(set(rule.get("any_terms", [])) for rule in mutation_rules))
    report.check(
        scoped_terms == effectful_terms,
        f"scoped mutation vocabulary must equal effectful route terms: expected={sorted(effectful_terms)}, actual={sorted(scoped_terms)}",
    )
    read_only_terms = set().union(*(
        set(rule.get("any_terms", [])) for rule in route_rules if rule.get("value") == "read-only"
    ))
    report.check(not (read_only_terms & scoped_terms), "read-only vocabulary must not independently grant scoped mutation")
    ids: set[str] = set()
    for index, fixture in enumerate(fixtures):
        label = f"router fixture #{index + 1}"
        if not isinstance(fixture, dict):
            report.errors.append(f"{label} must be an object")
            continue
        fixture_id = fixture.get("id")
        request = fixture.get("request")
        expected_route = fixture.get("route")
        expected_mutation = fixture.get("mutation")
        report.check(isinstance(fixture_id, str) and bool(fixture_id), f"{label} requires an id")
        report.check(fixture_id not in ids, f"duplicate router fixture id: {fixture_id!r}")
        report.check(isinstance(request, str) and bool(request.strip()), f"{label} requires a request")
        report.check(expected_route in known_routes, f"{label} has unknown route {expected_route!r}")
        report.check(expected_mutation in known_mutations, f"{label} has unknown mutation {expected_mutation!r}")
        ids.add(str(fixture_id))
        if not isinstance(request, str):
            continue
        actual = classify_router_request(request, contract)
        actual_route = actual["route"]
        actual_mutation = actual["mutation"]
        report.check(actual_route == expected_route,
                     f"{fixture_id}: route contract produced {actual_route!r}, expected {expected_route!r}")
        report.check(actual_mutation == expected_mutation,
                     f"{fixture_id}: mutation contract produced {actual_mutation!r}, expected {expected_mutation!r}")
    report.ran(f"router contract ({len(fixtures)} fixtures)")


def validate_against_schema(
    value: Any,
    schema: dict[str, Any],
    *,
    root_schema: dict[str, Any] | None = None,
    path: str = "$",
) -> list[str]:
    """Compatibility wrapper over the shared fail-closed schema subset."""

    issues = _validate_schema_subset(value, schema, root_schema=root_schema)
    return [f"{path}{'' if issue.path == '/' else issue.path}: {issue.code}: {issue.message}" for issue in issues]


def check_feature_contract(report: Report) -> None:
    present = [FEATURE_SCHEMA.exists(), FEATURE_EXAMPLES.exists(), FEATURE_VALIDATOR.exists()]
    if not any(present):
        report.ran("feature contract (not present)")
        return
    report.check(all(present),
                 "feature contract must include schema, assets/contracts examples, and validator CLI together")
    if not all(present):
        return
    schema = load_json(FEATURE_SCHEMA, report)
    if not isinstance(schema, dict):
        return
    report.check(schema.get("$schema", "").startswith("https://json-schema.org/"),
                 "feature contract schema must identify its JSON Schema dialect")
    examples = sorted(FEATURE_EXAMPLES.glob("*.json"))
    standalone_example = POINT_SKILL / "assets" / "feature-contract.example.json"
    if standalone_example.is_file():
        examples.append(standalone_example)
        examples.sort()
    report.check(bool(examples), "feature contract requires canonical JSON examples")
    valid_count = invalid_count = 0
    for path in examples:
        payload = load_json(path, report)
        if payload is None:
            continue
        errors = validate_against_schema(payload, schema)
        expected_invalid = "invalid" in path.stem.casefold()
        if expected_invalid:
            invalid_count += 1
            # Some negative canaries are structurally valid but violate the
            # semantic relationships covered by the companion validator.
        else:
            valid_count += 1
            for error in errors:
                report.errors.append(f"{path.relative_to(ROOT)}: {error}")
    report.check(valid_count > 0, "feature contract requires at least one valid example")
    report.check(invalid_count > 0, "feature contract requires at least one invalid regression example")
    completed = subprocess.run(
        [sys.executable, str(FEATURE_VALIDATOR), "--self-test"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode:
        report.errors.append(
            "feature-contract validator self-test failed: "
            + (completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}")
        )
    report.ran(f"feature contract ({len(examples)} examples)")


def tree_digest(directory: Path) -> tuple[str, int]:
    """Return sha256-tree-v1 for a directory and its regular-file count."""

    digest = hashlib.sha256()
    count = 0
    for path in sorted(candidate for candidate in directory.rglob("*") if candidate.is_file() or candidate.is_symlink()):
        relative = path.relative_to(directory).as_posix()
        if any(part == "__pycache__" for part in path.parts) or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            content = os.readlink(path).encode("utf-8")
            mode = "120000"
        else:
            content = path.read_bytes()
            mode = "100755" if path.stat().st_mode & 0o111 else "100644"
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(mode.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
        digest.update(b"\0")
        count += 1
    return digest.hexdigest(), count


def check_vendor_lock(report: Report) -> None:
    lock = load_json(VENDOR_LOCK, report)
    if not isinstance(lock, dict):
        return
    report.check(lock.get("hash_algorithm") == "sha256-tree-v1",
                 "vendor-lock.json must use sha256-tree-v1")
    source = lock.get("source", {})
    report.check(source.get("repository") == "https://github.com/earthtojake/text-to-cad",
                 "vendor lock must retain the upstream repository")
    report.check(bool(re.fullmatch(r"[0-9a-f]{40}", str(source.get("commit", "")))),
                 "vendor lock source commit must be a full Git SHA")
    report.check(bool(re.fullmatch(r"\d+\.\d+\.\d+", str(source.get("tag", "")))),
                 "vendor lock source tag must be a semantic version")
    report.check(bool(re.fullmatch(r"[0-9a-f]{40}", str(lock.get("imported_in", "")))),
                 "vendor lock imported_in must be a full Git SHA")
    entries = lock.get("skills")
    if not isinstance(entries, list):
        report.errors.append("vendor-lock.json skills must be an array")
        return
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            report.errors.append("vendor-lock.json skill entries must be objects")
            continue
        relative = entry.get("path", "")
        report.check(relative not in seen, f"duplicate vendor-lock path {relative!r}")
        seen.add(relative)
        directory = ROOT / relative
        report.check(directory.is_dir(), f"vendored skill path is missing: {relative}")
        if not directory.is_dir():
            continue
        actual_hash, actual_count = tree_digest(directory)
        report.check(entry.get("sha256") == actual_hash,
                     f"vendored tree changed without lock update: {relative}")
        report.check(entry.get("files") == actual_count,
                     f"vendored file count changed without lock update: {relative}")
    expected = {path.parent.relative_to(ROOT).as_posix() for path in (ROOT / "skills").glob("*/SKILL.md")
                if path.parent.name != "point-cloud-reverse-engineering"}
    report.check(seen == expected,
                 f"vendor lock paths differ from companion skills: missing={sorted(expected-seen)}, extra={sorted(seen-expected)}")
    report.ran(f"vendor lock ({len(entries)} skill trees)")


SECRET_PATTERNS = (
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"), "private key material"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"), "GitHub token"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "API token"),
    (re.compile(r"(?i)\bDATABASE_URL\s*=\s*[^\s<{][^\s]*"), "database connection string"),
    (re.compile(r"/home/(?!user\b|runner\b|\{)[A-Za-z0-9._-]+"), "machine-specific home path"),
    (re.compile(r"/Users/(?!me\b|user\b|runner\b|\{)[A-Za-z0-9._-]+"), "machine-specific macOS path"),
    (re.compile(r"(?i)C:[\\/]+Users[\\/]+(?!user\b|runner\b|\{)[A-Za-z0-9._-]+"), "machine-specific Windows path"),
    (re.compile(r"(?:^|/)\.gbrain(?:/|$)"), "private-memory path"),
)


def repository_text_files() -> Iterable[Path]:
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or any(part in {".git", "dist", "__pycache__"} for part in path.parts):
            continue
        relative_parts = path.relative_to(ROOT).parts
        # Companion skills are byte-locked copies of a public upstream tree;
        # scan authored plugin/CI content here and enforce those copies through
        # the vendor lock instead of flagging their portable path test vectors.
        if (len(relative_parts) >= 2 and relative_parts[0] == "skills"
                and relative_parts[1] != "point-cloud-reverse-engineering"):
            continue
        if path.suffix in {".map", ".pyc", ".pyo", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".zip"}:
            continue
        if path.stat().st_size > 2_000_000:
            continue
        yield path


def check_privacy_canaries(report: Report) -> None:
    checked = 0
    for path in repository_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        checked += 1
        for pattern, label in SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                report.errors.append(f"{path.relative_to(ROOT)}:{line}: privacy canary found {label}")
    report.ran(f"privacy/path canaries ({checked} authored files)")


def check_root_metadata(report: Report) -> None:
    compatibility = load_json(ROOT / "compatibility.json", report)
    distribution = load_json(ROOT / "distribution.json", report)
    if isinstance(compatibility, dict):
        report.check(compatibility.get("schema_version") == 1, "compatibility.json schema_version must be 1")
        components = compatibility.get("components")
        routes = compatibility.get("routes")
        required_components = {
            "blender",
            "blender_python_abi",
            "host_python",
            "cad_sketcher",
            "agent_bridge",
            "agent_bridge_command",
            "open3d",
            "cloudcompare",
            "autodesk_fusion",
        }
        report.check(isinstance(components, dict) and required_components <= set(components),
                     "compatibility.json must cover Fusion, Blender, Python ABI, CAD Sketcher, bridge, Open3D, and CloudCompare")
        report.check(isinstance(routes, dict) and bool(routes), "compatibility.json must describe route compatibility")
    if isinstance(distribution, dict):
        report.check(distribution.get("schema_version") == 1, "distribution.json schema_version must be 1")
        profiles = distribution.get("profiles")
        report.check(isinstance(profiles, dict) and {"core", "full"} <= set(profiles or {}),
                     "distribution.json must define core and full profiles")
    report.ran("compatibility/distribution metadata")


def validate_repository() -> Report:
    report = Report()
    check_manifests(report)
    check_skill_frontmatter(report)
    check_relative_markdown_links(report)
    check_router_fixtures(report)
    check_feature_contract(report)
    check_vendor_lock(report)
    check_root_metadata(report)
    check_privacy_canaries(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    args = parser.parse_args(argv)
    report = validate_repository()
    payload = {"ok": not report.errors, "checks": report.checks, "errors": report.errors}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for check in report.checks:
            print(f"ok: {check}")
        for error in report.errors:
            print(f"error: {error}", file=sys.stderr)
        print(f"repository validation: {'ok' if not report.errors else 'failed'}")
    return 0 if not report.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
