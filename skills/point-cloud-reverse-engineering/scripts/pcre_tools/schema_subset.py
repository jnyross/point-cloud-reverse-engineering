"""Fail-closed dependency-free subset of JSON Schema Draft 2020-12.

Only the assertion vocabulary used by the bundled feature-contract schema is
implemented.  Schema documents are checked before use; an unknown assertion
keyword is an error rather than a silently ignored constraint.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Set


ANNOTATION_KEYWORDS = {
    "$schema", "$id", "$comment", "title", "description", "default",
    "examples", "deprecated", "readOnly", "writeOnly",
}
ASSERTION_KEYWORDS = {
    "$ref", "type", "const", "enum", "required", "properties",
    "additionalProperties", "items", "prefixItems", "minItems", "maxItems",
    "uniqueItems", "contains", "minContains", "maxContains", "minLength",
    "maxLength", "pattern", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "allOf", "anyOf", "oneOf", "not", "if", "then",
    "else", "dependentRequired",
}
CONTAINER_KEYWORDS = {"$defs"}
SUPPORTED_KEYWORDS = ANNOTATION_KEYWORDS | ASSERTION_KEYWORDS | CONTAINER_KEYWORDS
MAX_SCHEMA_ISSUES = 256
MAX_SCHEMA_VISITS = 500_000
MAX_INSTANCE_NODES = 200_000
MAX_INSTANCE_DEPTH = 256
JSON_TYPE_NAMES = {"null", "boolean", "object", "array", "number", "integer", "string"}


@dataclass(frozen=True)
class SchemaIssue:
    code: str
    path: str
    message: str

    def as_dict(self) -> Dict[str, str]:
        return asdict(self)


def _pointer(parent: str, token: Any) -> str:
    escaped = str(token).replace("~", "~0").replace("/", "~1")
    return parent + "/" + escaped if parent else "/" + escaped


def _schema_children(schema: Mapping[str, Any], path: str) -> Iterator[tuple[Any, str]]:
    for keyword in ("$defs", "properties"):
        value = schema.get(keyword)
        if isinstance(value, Mapping):
            for name, child in value.items():
                yield child, _pointer(_pointer(path, keyword), name)
    for keyword in ("additionalProperties", "items", "contains", "not", "if", "then", "else"):
        value = schema.get(keyword)
        if isinstance(value, (Mapping, bool)):
            yield value, _pointer(path, keyword)
    for keyword in ("prefixItems", "allOf", "anyOf", "oneOf"):
        value = schema.get(keyword)
        if isinstance(value, list):
            for index, child in enumerate(value):
                yield child, _pointer(_pointer(path, keyword), index)


def _valid_keyword_shape(keyword: str, value: Any) -> bool:
    schema_node = lambda candidate: isinstance(candidate, (Mapping, bool))
    if keyword in ("$schema", "$id", "$comment", "title", "description"):
        return isinstance(value, str)
    if keyword == "examples":
        return isinstance(value, list)
    if keyword in ("deprecated", "readOnly", "writeOnly"):
        return isinstance(value, bool)
    if keyword == "default":
        return True
    if keyword == "$ref":
        return isinstance(value, str) and value.startswith("#/")
    if keyword == "type":
        return (isinstance(value, str) and value in JSON_TYPE_NAMES) or (
            isinstance(value, list)
            and bool(value)
            and all(isinstance(item, str) and item in JSON_TYPE_NAMES for item in value)
            and len(value) == len(set(value))
        )
    if keyword in ("required",):
        return isinstance(value, list) and all(isinstance(item, str) for item in value) and len(value) == len(set(value))
    if keyword in ("properties", "$defs"):
        return isinstance(value, Mapping) and all(isinstance(name, str) and schema_node(child) for name, child in value.items())
    if keyword in ("additionalProperties", "items", "contains", "not", "if", "then", "else"):
        return schema_node(value)
    if keyword in ("prefixItems", "allOf", "anyOf", "oneOf"):
        return isinstance(value, list) and bool(value) and all(schema_node(child) for child in value)
    if keyword in ("minItems", "maxItems", "minContains", "maxContains", "minLength", "maxLength"):
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if keyword == "uniqueItems":
        return isinstance(value, bool)
    if keyword == "pattern":
        if not isinstance(value, str):
            return False
        try:
            re.compile(value)
        except re.error:
            return False
        return True
    if keyword in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and _finite_number(value)
    if keyword == "enum":
        if not isinstance(value, list) or not value or len(value) > MAX_INSTANCE_NODES:
            return False
        try:
            keys = [_unique_key(item) for item in value]
        except (RecursionError, TypeError, ValueError):
            return False
        return len(keys) == len(set(keys))
    if keyword == "dependentRequired":
        return isinstance(value, Mapping) and all(
            isinstance(name, str)
            and isinstance(dependencies, list)
            and all(isinstance(item, str) for item in dependencies)
            and len(dependencies) == len(set(dependencies))
            for name, dependencies in value.items()
        )
    return True


def check_supported_schema(schema: Any) -> List[SchemaIssue]:
    """Reject unsupported assertion keywords anywhere in a schema tree."""

    issues: List[SchemaIssue] = []
    pending: List[tuple[Any, str]] = [(schema, "")]
    visited = 0
    while pending:
        visited += 1
        if visited > MAX_SCHEMA_VISITS or len(issues) >= MAX_SCHEMA_ISSUES:
            return [SchemaIssue("schema.resource_budget", "/", "schema audit exceeded its hard node or issue budget")]
        node, path = pending.pop()
        if isinstance(node, bool):
            continue
        if not isinstance(node, Mapping):
            issues.append(SchemaIssue("schema.invalid_node", path or "/", "schema node must be an object or boolean"))
            continue
        for keyword in node:
            if keyword not in SUPPORTED_KEYWORDS:
                issues.append(
                    SchemaIssue(
                        "schema.unsupported_keyword",
                        _pointer(path, keyword),
                        "unsupported schema keyword %r; constraint would otherwise be ignored" % keyword,
                    )
                )
            elif not _valid_keyword_shape(keyword, node[keyword]):
                issues.append(
                    SchemaIssue(
                        "schema.invalid_keyword_value",
                        _pointer(path, keyword),
                        "schema keyword %r has an unsupported or invalid value" % keyword,
                    )
                )
            if len(issues) >= MAX_SCHEMA_ISSUES:
                return [SchemaIssue("schema.resource_budget", "/", "schema audit exceeded its hard node or issue budget")]
        for child in _schema_children(node, path):
            if visited + len(pending) >= MAX_SCHEMA_VISITS:
                return [SchemaIssue("schema.resource_budget", "/", "schema audit exceeded its hard node or issue budget")]
            pending.append(child)
    return sorted(issues, key=lambda issue: (issue.path, issue.code))


def _preflight_instance(instance: Any) -> Optional[SchemaIssue]:
    pending: List[tuple[Any, int]] = [(instance, 0)]
    visited = 0
    while pending:
        value, depth = pending.pop()
        visited += 1
        if visited > MAX_INSTANCE_NODES:
            return SchemaIssue("schema.resource_budget", "/", "JSON instance exceeds the hard node budget")
        if depth > MAX_INSTANCE_DEPTH:
            return SchemaIssue("schema.resource_budget", "/", "JSON instance exceeds the hard nesting-depth budget")
        if isinstance(value, Mapping):
            if visited + len(pending) + len(value) > MAX_INSTANCE_NODES:
                return SchemaIssue("schema.resource_budget", "/", "JSON instance exceeds the hard node budget")
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            if visited + len(pending) + len(value) > MAX_INSTANCE_NODES:
                return SchemaIssue("schema.resource_budget", "/", "JSON instance exceeds the hard node budget")
            pending.extend((child, depth + 1) for child in value)
    return None


class _ValidationBudgetExceeded(RuntimeError):
    pass


def _resolve_ref(root: Mapping[str, Any], reference: Any) -> Any:
    if not isinstance(reference, str) or not reference.startswith("#/"):
        raise ValueError("only local JSON-pointer $ref values are supported")
    value: Any = root
    for raw in reference[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, Mapping) or token not in value:
            raise ValueError("unresolvable $ref %r" % reference)
        value = value[token]
    return value


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "unknown"


def _matches_type(value: Any, expected: str) -> bool:
    actual = _json_type(value)
    if expected == "integer" and isinstance(value, float):
        return math.isfinite(value) and value.is_integer()
    return actual == expected or (expected == "number" and actual == "integer")


def _json_equal(left: Any, right: Any) -> bool:
    left_type = _json_type(left)
    right_type = _json_type(right)
    if {left_type, right_type} <= {"integer", "number"}:
        # Python compares arbitrary-size integers and finite floats without
        # requiring a lossy/overflowing eager float conversion.
        return left == right
    if left_type != right_type:
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(_json_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, Mapping):
        return set(left) == set(right) and all(_json_equal(left[key], right[key]) for key in left)
    return left == right


def _unique_key(value: Any) -> Any:
    """Return a hashable JSON-semantic key (not a textual encoding key)."""

    kind = _json_type(value)
    if kind in ("integer", "number"):
        # Python numeric equality/hashing correctly makes JSON 1 and 1.0 the
        # same value while the explicit kind keeps booleans separate.
        return ("number", value)
    if kind == "array":
        return ("array", tuple(_unique_key(item) for item in value))
    if kind == "object":
        return ("object", tuple(sorted((key, _unique_key(child)) for key, child in value.items())))
    if kind in ("string", "boolean", "null"):
        return (kind, value)
    return ("non-json", type(value).__name__, repr(value))


def _finite_number(value: Any) -> bool:
    if isinstance(value, int) and not isinstance(value, bool):
        return True
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def validate_instance(instance: Any, schema: Any, *, root_schema: Any = None) -> List[SchemaIssue]:
    """Validate an instance after ``check_supported_schema`` succeeds."""

    authority = schema if root_schema is None else root_schema
    schema_issues = check_supported_schema(authority)
    if schema_issues:
        return schema_issues
    preflight_issue = _preflight_instance(instance)
    if preflight_issue is not None:
        return [preflight_issue]
    if not isinstance(schema, Mapping):
        if schema is True:
            return []
        return [SchemaIssue("schema.false", "/", "root false schema rejects every instance")]
    issues: List[SchemaIssue] = []
    visit_count = 0
    issue_count = 0
    active_references: Set[tuple[str, str]] = set()

    def issue(code: str, path: str, message: str, *, charge: bool = True) -> SchemaIssue:
        nonlocal issue_count
        if charge:
            issue_count += 1
            if issue_count > MAX_SCHEMA_ISSUES:
                raise _ValidationBudgetExceeded
        return SchemaIssue(code, path, message)

    def visit(value: Any, node: Any, path: str, *, probe: bool = False) -> List[SchemaIssue]:
        nonlocal visit_count
        visit_count += 1
        if visit_count > MAX_SCHEMA_VISITS:
            raise _ValidationBudgetExceeded
        def emit(code: str, issue_path: str, message: str) -> SchemaIssue:
            return issue(code, issue_path, message, charge=not probe)
        if node is True:
            return []
        if node is False:
            return [emit("schema.false", path or "/", "value is rejected by false schema")]
        if not isinstance(node, Mapping):
            return [emit("schema.invalid_node", path or "/", "schema node must be object or boolean")]
        local: List[SchemaIssue] = []
        if "$ref" in node:
            reference = node["$ref"]
            reference_key = (str(reference), path)
            if reference_key in active_references:
                return [emit("schema.ref_cycle", path or "/", "cyclic schema reference does not advance the instance path")]
            try:
                target = _resolve_ref(authority, reference)
            except ValueError as error:
                return [emit("schema.ref", path or "/", str(error))]
            active_references.add(reference_key)
            try:
                local.extend(visit(value, target, path, probe=probe))
            finally:
                active_references.remove(reference_key)

        declared = node.get("type")
        expected_types: Set[str] = {declared} if isinstance(declared, str) else set(declared or [])
        if expected_types and not any(_matches_type(value, expected) for expected in expected_types):
            return [emit("schema.type", path or "/", "expected %s, got %s" % (sorted(expected_types), _json_type(value)))]
        if "const" in node and not _json_equal(value, node["const"]):
            local.append(emit("schema.const", path or "/", "value does not equal required const"))
        if "enum" in node and not any(_json_equal(value, option) for option in node["enum"]):
            local.append(emit("schema.enum", path or "/", "value is not in the allowed enum"))

        for child in node.get("allOf", []):
            local.extend(visit(value, child, path, probe=probe))
        for keyword, exactly_one in (("anyOf", False), ("oneOf", True)):
            if keyword in node:
                branch_results = [visit(value, child, path, probe=True) for child in node[keyword]]
                matches = sum(not result for result in branch_results)
                if matches == 0 or (exactly_one and matches != 1):
                    local.append(emit("schema." + keyword, path or "/", "%s matched %d branches" % (keyword, matches)))
        if "not" in node and not visit(value, node["not"], path, probe=True):
            local.append(emit("schema.not", path or "/", "value matched a forbidden schema"))
        if "if" in node:
            condition_matches = not visit(value, node["if"], path, probe=True)
            branch = node.get("then") if condition_matches else node.get("else")
            if branch is not None:
                local.extend(visit(value, branch, path, probe=probe))

        if isinstance(value, Mapping):
            for name in node.get("required", []):
                if name not in value:
                    local.append(emit("schema.required", _pointer(path, name), "required property is missing"))
            properties = node.get("properties", {})
            for name, child_value in value.items():
                child_path = _pointer(path, name)
                if name in properties:
                    local.extend(visit(child_value, properties[name], child_path, probe=probe))
                elif node.get("additionalProperties") is False:
                    local.append(
                        emit(
                            "schema.additional_property",
                            _pointer(path, "<redacted-property>"),
                            "an undeclared property is not allowed",
                        )
                    )
                elif isinstance(node.get("additionalProperties"), (Mapping, bool)):
                    local.extend(visit(child_value, node["additionalProperties"], child_path, probe=probe))
            for name, dependencies in node.get("dependentRequired", {}).items():
                if name in value:
                    for dependency in dependencies:
                        if dependency not in value:
                            local.append(emit("schema.dependent_required", _pointer(path, dependency), "property is required when %r is present" % name))

        if isinstance(value, list):
            if "minItems" in node and len(value) < node["minItems"]:
                local.append(emit("schema.min_items", path or "/", "array has fewer than %d items" % node["minItems"]))
            if "maxItems" in node and len(value) > node["maxItems"]:
                local.append(emit("schema.max_items", path or "/", "array has more than %d items" % node["maxItems"]))
                return local
            if node.get("uniqueItems"):
                encoded = [_unique_key(item) for item in value]
                if len(encoded) != len(set(encoded)):
                    local.append(emit("schema.unique_items", path or "/", "array items are not unique"))
            prefix = node.get("prefixItems", [])
            for index, item in enumerate(value):
                child_schema = prefix[index] if index < len(prefix) else node.get("items")
                if child_schema is not None:
                    local.extend(visit(item, child_schema, _pointer(path, index), probe=probe))
            if "contains" in node:
                matches = sum(not visit(item, node["contains"], _pointer(path, index), probe=True) for index, item in enumerate(value))
                minimum = node.get("minContains", 1)
                maximum = node.get("maxContains")
                if matches < minimum:
                    local.append(emit("schema.contains", path or "/", "contains matched %d items; needs %d" % (matches, minimum)))
                if maximum is not None and matches > maximum:
                    local.append(emit("schema.contains", path or "/", "contains matched %d items; maximum is %d" % (matches, maximum)))

        if isinstance(value, str):
            if "minLength" in node and len(value) < node["minLength"]:
                local.append(emit("schema.min_length", path or "/", "string is too short"))
            if "maxLength" in node and len(value) > node["maxLength"]:
                local.append(emit("schema.max_length", path or "/", "string is too long"))
            if "pattern" in node:
                try:
                    matched = re.search(node["pattern"], value) is not None
                except re.error as error:
                    local.append(emit("schema.pattern", path or "/", "invalid schema regex: %s" % error))
                else:
                    if not matched:
                        local.append(emit("schema.pattern", path or "/", "string does not match required pattern"))

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not _finite_number(value):
                local.append(emit("schema.finite", path or "/", "number must be finite JSON data"))
            for keyword, predicate in (
                ("minimum", lambda left, right: left >= right),
                ("maximum", lambda left, right: left <= right),
                ("exclusiveMinimum", lambda left, right: left > right),
                ("exclusiveMaximum", lambda left, right: left < right),
            ):
                if keyword in node and not predicate(value, node[keyword]):
                    local.append(emit("schema." + keyword, path or "/", "number violates %s %s" % (keyword, node[keyword])))
        return local

    try:
        issues.extend(visit(instance, schema, ""))
    except (_ValidationBudgetExceeded, RecursionError):
        return [SchemaIssue("schema.resource_budget", "/", "validation exceeded its hard node or issue budget")]
    return sorted(issues, key=lambda issue: (issue.path, issue.code, issue.message))
