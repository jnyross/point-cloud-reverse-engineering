"""Schema-aligned semantic validation for the feature contract.

The JSON Schema is the portable structural authority.  This module deliberately
uses only the Python standard library and adds checks JSON Schema cannot express:
matrix geometry, reference integrity, artifact lineage, metric consistency,
uncertainty arithmetic, and accidental private-path leakage.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import stat
from collections import deque
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableSequence, Optional, Sequence, Set, Tuple

from .schema_subset import check_supported_schema, validate_instance


SCHEMA_VERSION = "1.0.0"
VALIDATOR_VERSION = "pcre-contract-stdlib-1.0"
SCHEMA_ID = "urn:jnyross:point-cloud-reverse-engineering:feature-contract:1.0.0"
ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALGORITHM_VERSION_RE = re.compile(r"[a-z0-9][a-z0-9.-]{0,31}")
MEDIA_TYPE_RE = re.compile(r"[a-z0-9.+-]+/[a-z0-9.+-]+")
WINDOWS_ABSOLUTE_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
WINDOWS_ROOTED_RE = re.compile(r"(?<![\\A-Za-z0-9])\\(?!\\)[^\\\s]+(?:\\[^\\\s]+)+")
SECRET_KEY_RE = re.compile(r"(?:password|passwd|credential|secret|access[_-]?token|api[_-]?key)", re.I)
SIGNED_URL_RE = re.compile(r"(?:x-amz-signature|x-goog-signature|sig=|token=)", re.I)
UNC_ABSOLUTE_RE = re.compile(r"(?<![\\/])(?:\\\\|//)[^\\/\s]+[\\/][^\\/\s]+")
POSIX_ABSOLUTE_RE = re.compile(r"(?<![A-Za-z0-9._~-])/(?:[^/\s]+/)*[^/\s]+")
HOME_ABSOLUTE_RE = re.compile(r"(?<![A-Za-z0-9._~-])~/[^\s]+")
RELATIVE_PATH_RE = re.compile(r"(?<![A-Za-z0-9._~-])(?:\.\.?[\\/])[^\s]+")
HOME_VARIABLE_RE = re.compile(r"(?:\$HOME|\$\{HOME\}|%(?:USERPROFILE|HOME)%)[\\/][^\s]+", re.I)
URI_RE = re.compile(r"\b[a-z][a-z0-9+.-]{1,31}://[^\s]+", re.I)
HOSTNAME_RE = re.compile(r"(?<![@A-Za-z0-9_-])(?:[A-Za-z0-9-]+\.)+(?:local|internal|lan|home|corp|private|test|invalid|[A-Za-z]{2,63})(?::[0-9]{1,5})?(?![A-Za-z0-9_-])", re.I)
NETWORK_LITERAL_RE = re.compile(r"(?<![A-Za-z0-9])(?:\[(?P<ipv6>[0-9A-Fa-f:]+)\]|(?P<ipv4>(?:[0-9]{1,3}\.){3}[0-9]{1,3}))(?::[0-9]{1,5})?(?![A-Za-z0-9])")
BARE_IPV6_RE = re.compile(r"(?<![A-Za-z0-9])(?P<ipv6>[0-9A-Fa-f:]*:[0-9A-Fa-f:]*:[0-9A-Fa-f:]*(?:%[A-Za-z0-9_.-]+)?)(?![A-Za-z0-9])")
LOCALHOST_RE = re.compile(r"(?<![A-Za-z0-9_-])localhost(?::[0-9]{1,5})?(?![A-Za-z0-9_-])", re.I)
CREDENTIAL_VALUE_RE = re.compile(
    r"(?:\b(?:password|passwd|api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|token)\s*[:=]\s*\S+"
    r"|\bauthorization\s*:\s*(?:bearer|basic)\s+\S+"
    r"|-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
    r"|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b)",
    re.I,
)
MAX_JSON_INTEGER = 2**63 - 1
MAX_EXACT_EVIDENCE_INTEGER = 2**53 - 1
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_SEMANTIC_DIAGNOSTICS = 256
MAX_EVIDENCE_REASONS = 32
MAX_REALIZABILITY_BLOCKS = 64
REQUIRED_PERCENTILE_PROFILE = (50.0, 95.0, 98.0, 99.0)
POINT_EVIDENCE_FORMATS = {"xyz", "asc", "txt", "pts", "csv", "ply", "e57", "las", "laz"}
DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "assets" / "feature-contract.schema.json"


@dataclass(frozen=True)
class Issue:
    level: str
    code: str
    path: str
    message: str


class Findings:
    def __init__(self) -> None:
        self.errors: List[Issue] = []
        self.warnings: List[Issue] = []
        self._truncated = False

    def _add(self, issue: Issue) -> None:
        if self._truncated:
            return
        if len(self.errors) + len(self.warnings) >= MAX_SEMANTIC_DIAGNOSTICS - 1:
            self.errors.append(
                Issue(
                    "error",
                    "validation.resource_budget",
                    "/",
                    "validation diagnostics exceeded the hard output budget",
                )
            )
            self._truncated = True
            return
        if issue.level == "error":
            self.errors.append(issue)
        else:
            self.warnings.append(issue)

    def error(self, code: str, path: str, message: str) -> None:
        self._add(Issue("error", code, path, message))

    def warning(self, code: str, path: str, message: str) -> None:
        self._add(Issue("warning", code, path, message))

    def report(
        self,
        contract: Any,
        evidence_status: str = "not-evaluated",
        evidence_results: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> Dict[str, Any]:
        contract_id = contract.get("contract_id") if isinstance(contract, Mapping) else None
        schema_version = contract.get("schema_version") if isinstance(contract, Mapping) else None
        contract_valid = not self.errors
        return {
            "ok": contract_valid and evidence_status == "pass",
            "contract_valid": contract_valid,
            "evidence_status": evidence_status,
            "evidence_results": list(evidence_results or []),
            "validator": VALIDATOR_VERSION,
            "schema_id": SCHEMA_ID,
            "schema_version": schema_version,
            "contract_id": contract_id,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [asdict(item) for item in self.errors],
            "warnings": [asdict(item) for item in self.warnings],
        }


def _reject_non_json_constant(value: str) -> None:
    raise ValueError("non-JSON numeric constant: %s" % value)


def _parse_bounded_int(value: str) -> int:
    if len(value.lstrip("-")) > 19:
        raise ValueError("JSON integer exceeds signed 64-bit contract range")
    parsed = int(value)
    if abs(parsed) > MAX_JSON_INTEGER:
        raise ValueError("JSON integer exceeds signed 64-bit contract range")
    return parsed


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("JSON number overflows finite contract range")
    if parsed == 0:
        try:
            exact = Decimal(value)
        except InvalidOperation as error:
            raise ValueError("JSON number is not a valid finite decimal") from error
        if not exact.is_zero():
            raise ValueError("JSON number underflows the supported IEEE-754 range")
    return parsed


def _reject_duplicate_object_keys(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    decoded: Dict[str, Any] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError("JSON object contains a duplicate key")
        decoded[key] = value
    return decoded


def load_json_strict(path: Path) -> Any:
    """Load strict JSON, rejecting NaN and infinities accepted by json.loads."""

    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("JSON input must be a regular file")
        payload = handle.read(MAX_JSON_BYTES + 1)
    if len(payload) > MAX_JSON_BYTES:
        raise ValueError("JSON input exceeds the hard %d-byte size cap" % MAX_JSON_BYTES)
    return json.loads(
        payload.decode("utf-8"),
        parse_constant=_reject_non_json_constant,
        parse_int=_parse_bounded_int,
        parse_float=_parse_finite_float,
        object_pairs_hook=_reject_duplicate_object_keys,
    )


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _path(parent: str, child: Any) -> str:
    escaped = str(child).replace("~", "~0").replace("/", "~1")
    return parent + "/" + escaped if parent else "/" + escaped


def _is_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    if isinstance(value, int):
        return abs(value) <= MAX_JSON_INTEGER
    return math.isfinite(value)


def _require_object(
    value: Any,
    path: str,
    findings: Findings,
    required: Iterable[str] = (),
    allowed: Optional[Iterable[str]] = None,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        findings.error("structure.object", path, "expected an object")
        return {}
    for key in required:
        if key not in value:
            findings.error("structure.required", _path(path, key), "required property is missing")
    if allowed is not None:
        allowed_set = set(allowed)
        for key in value:
            if key not in allowed_set:
                findings.error("structure.additional_property", _path(path, key), "property is not allowed by schema 1.0.0")
    return value


def _require_array(value: Any, path: str, findings: Findings, minimum: int = 0) -> Sequence[Any]:
    if not isinstance(value, list):
        findings.error("structure.array", path, "expected an array")
        return []
    if len(value) < minimum:
        findings.error("structure.min_items", path, "expected at least %d item(s)" % minimum)
    return value


def _check_id(value: Any, path: str, findings: Findings) -> Optional[str]:
    if not isinstance(value, str) or not ID_RE.fullmatch(value) or len(value) > 80:
        findings.error("structure.id", path, "expected a portable kebab-case identifier")
        return None
    return value


def _check_sha(value: Any, path: str, findings: Findings) -> Optional[str]:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        findings.error("structure.sha256", path, "expected a lowercase 64-character SHA-256 digest")
        return None
    return value


def _check_number(
    value: Any,
    path: str,
    findings: Findings,
    minimum: Optional[float] = None,
    exclusive: bool = False,
) -> Optional[float]:
    if not _is_number(value):
        findings.error("structure.number", path, "expected a finite JSON number")
        return None
    number = float(value)
    if minimum is not None and ((exclusive and number <= minimum) or (not exclusive and number < minimum)):
        relation = "greater than" if exclusive else "at least"
        findings.error("structure.minimum", path, "expected a value %s %s" % (relation, minimum))
        return None
    return number


def _as_integer(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def _check_integer(value: Any, path: str, findings: Findings, minimum: int = 0) -> Optional[int]:
    integer = _as_integer(value)
    if integer is None:
        findings.error("structure.integer", path, "expected an integer")
        return None
    if abs(integer) > MAX_JSON_INTEGER:
        findings.error("structure.integer_range", path, "integer exceeds the signed 64-bit contract range")
        return None
    if integer < minimum:
        findings.error("structure.minimum", path, "expected an integer at least %d" % minimum)
        return None
    return integer


def _check_vector3(value: Any, path: str, findings: Findings) -> Optional[Tuple[float, float, float]]:
    items = _require_array(value, path, findings)
    if len(items) != 3:
        findings.error("structure.vector3", path, "expected exactly three finite coordinates")
        return None
    numbers = [_check_number(item, _path(path, index), findings) for index, item in enumerate(items)]
    if any(number is None for number in numbers):
        return None
    return (numbers[0], numbers[1], numbers[2])  # type: ignore[return-value]


def _check_unique_ids(items: Sequence[Any], path: str, findings: Findings) -> Set[str]:
    found: Set[str] = set()
    for index, raw in enumerate(items):
        item_path = _path(path, index)
        if not isinstance(raw, Mapping):
            continue
        item_id = _check_id(raw.get("id"), _path(item_path, "id"), findings)
        if item_id is not None:
            if item_id in found:
                findings.error("reference.duplicate_id", _path(item_path, "id"), "identifier is duplicated in this collection")
            found.add(item_id)
    return found


def _check_artifact(value: Any, path: str, findings: Findings) -> Mapping[str, Any]:
    artifact = _require_object(
        value,
        path,
        findings,
        required=("sha256", "byte_count", "format"),
        allowed=("sha256", "byte_count", "format", "media_type"),
    )
    _check_sha(artifact.get("sha256"), _path(path, "sha256"), findings)
    _check_integer(artifact.get("byte_count"), _path(path, "byte_count"), findings, 1)
    fmt = artifact.get("format")
    if not isinstance(fmt, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._+-]{0,31}", fmt):
        findings.error("structure.format", _path(path, "format"), "expected a short lowercase portable format name")
    media_type = artifact.get("media_type")
    if media_type is not None and (not isinstance(media_type, str) or MEDIA_TYPE_RE.fullmatch(media_type) is None):
        findings.error("structure.media_type", _path(path, "media_type"), "expected an IANA-style media type")
    return artifact


def _check_bounds(value: Any, path: str, findings: Findings, frame_ids: Set[str]) -> Mapping[str, Any]:
    bounds = _require_object(
        value,
        path,
        findings,
        required=("frame", "min", "max"),
        allowed=("frame", "min", "max"),
    )
    frame = _check_id(bounds.get("frame"), _path(path, "frame"), findings)
    if frame is not None and frame not in frame_ids:
        findings.error("reference.frame", _path(path, "frame"), "frame is not declared in /frames")
    lower = _check_vector3(bounds.get("min"), _path(path, "min"), findings)
    upper = _check_vector3(bounds.get("max"), _path(path, "max"), findings)
    if lower is not None and upper is not None:
        for axis, (minimum, maximum) in enumerate(zip(lower, upper)):
            if minimum > maximum:
                findings.error("geometry.bounds_order", _path(path, "max/%d" % axis), "maximum is below minimum")
    return bounds


def _walk_private_values(value: Any, path: str, findings: Findings) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = _path(path, key)
            if SECRET_KEY_RE.search(str(key)) and child not in (None, "", [], {}):
                findings.error("privacy.secret_field", child_path, "contracts must not contain credentials or secrets")
            _walk_private_values(child, child_path, findings)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_private_values(child, _path(path, index), findings)
    elif isinstance(value, str):
        stripped = value.strip()
        field_name = path.rsplit("/", 1)[-1]
        version_field = field_name in {"schema_version", "tool_version", "algorithm_version", "kernel"}
        if (
            POSIX_ABSOLUTE_RE.search(stripped)
            or HOME_ABSOLUTE_RE.search(stripped)
            or WINDOWS_ABSOLUTE_RE.search(stripped)
            or WINDOWS_ROOTED_RE.search(stripped)
            or UNC_ABSOLUTE_RE.search(stripped)
            or RELATIVE_PATH_RE.search(stripped)
            or HOME_VARIABLE_RE.search(stripped)
        ):
            findings.error("privacy.absolute_path", path, "replace private filesystem paths with content hashes")
        has_ip_literal = False
        if not version_field:
            for match in NETWORK_LITERAL_RE.finditer(stripped):
                candidate = match.group("ipv6") or match.group("ipv4")
                try:
                    ipaddress.ip_address(candidate)
                except ValueError:
                    continue
                has_ip_literal = True
                break
            if not has_ip_literal:
                for match in BARE_IPV6_RE.finditer(stripped):
                    candidate = match.group("ipv6").split("%", 1)[0]
                    try:
                        ipaddress.ip_address(candidate)
                    except ValueError:
                        continue
                    has_ip_literal = True
                    break
        if URI_RE.search(stripped) or HOSTNAME_RE.search(stripped) or LOCALHOST_RE.search(stripped) or has_ip_literal:
            findings.error("privacy.network_location", path, "replace URLs, bucket locations, and hostnames with content hashes")
        if CREDENTIAL_VALUE_RE.search(stripped):
            findings.error("privacy.secret_value", path, "contracts must not embed credentials or secret values in free text")
        if SIGNED_URL_RE.search(stripped):
            findings.error("privacy.signed_url", path, "signed or tokenized URLs must not be stored in a contract")


def _determinant3(matrix: Sequence[float]) -> float:
    a, b, c = matrix[0], matrix[1], matrix[2]
    d, e, f = matrix[4], matrix[5], matrix[6]
    g, h, i = matrix[8], matrix[9], matrix[10]
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def _matrix4_product(left: Sequence[float], right: Sequence[float]) -> List[float]:
    output: List[float] = []
    for row in range(4):
        for column in range(4):
            value = sum(left[row * 4 + index] * right[index * 4 + column] for index in range(4))
            if not math.isfinite(value):
                raise OverflowError("matrix product produced a non-finite value")
            output.append(value)
    return output


def _identity_residual(matrix: Sequence[float]) -> float:
    return max(
        abs(matrix[row * 4 + column] - (1.0 if row == column else 0.0))
        for row in range(4) for column in range(4)
    )


def _linear_infinity_norm(matrix: Sequence[float]) -> float:
    return max(sum(abs(matrix[row * 4 + column]) for column in range(3)) for row in range(3))


def _row3(matrix: Sequence[float], row: int) -> Tuple[float, float, float]:
    offset = row * 4
    return (matrix[offset], matrix[offset + 1], matrix[offset + 2])


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _check_transform_cycles(
    records: Sequence[Tuple[str, str, str, Sequence[float], Sequence[float]]],
    findings: Findings,
) -> None:
    """Require every alternate transform path to imply the same frame map."""

    adjacency: Dict[str, List[Tuple[str, Sequence[float], str]]] = {}
    for transform_id, source, target, matrix, inverse in records:
        adjacency.setdefault(source, []).append((target, matrix, transform_id))
        adjacency.setdefault(target, []).append((source, inverse, transform_id))
    identity = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    potentials: Dict[str, List[float]] = {}
    reported: Set[str] = set()
    for root in sorted(adjacency):
        if root in potentials:
            continue
        potentials[root] = identity
        pending = deque([root])
        while pending:
            current = pending.popleft()
            for neighbour, step, transform_id in adjacency.get(current, ()):
                try:
                    candidate = _matrix4_product(step, potentials[current])
                except OverflowError:
                    if transform_id not in reported:
                        findings.error("transform.overflow", "/transforms", "transform graph composition produced non-finite intermediate values")
                        reported.add(transform_id)
                    continue
                if neighbour not in potentials:
                    potentials[neighbour] = candidate
                    pending.append(neighbour)
                    continue
                expected = potentials[neighbour]
                residual = max(
                    abs(left - right) / max(1.0, abs(left), abs(right))
                    for left, right in zip(candidate, expected)
                )
                if residual > 1e-8 and transform_id not in reported:
                    findings.error(
                        "transform.cycle",
                        "/transforms",
                        "alternate transform paths disagree (relative cycle residual %.6g)" % residual,
                    )
                    reported.add(transform_id)


def _check_transforms(
    transforms: Sequence[Any],
    frame_ids: Set[str],
    frame_handedness: Mapping[str, str],
    source_record: Mapping[str, Any],
    findings: Findings,
) -> Tuple[List[Tuple[str, str]], Dict[str, Mapping[str, Any]]]:
    _check_unique_ids(transforms, "/transforms", findings)
    edges: List[Tuple[str, str]] = []
    transform_by_id: Dict[str, Mapping[str, Any]] = {}
    cycle_records: List[Tuple[str, str, str, Sequence[float], Sequence[float]]] = []
    pairs: Set[Tuple[str, str]] = set()
    source_record_frame = source_record.get("frame")
    source_record_bounds = source_record.get("bounds") if isinstance(source_record.get("bounds"), Mapping) else {}
    source_coordinate_extent = 1.0
    bound_values = [
        value
        for key in ("min", "max")
        for value in (source_record_bounds.get(key) if isinstance(source_record_bounds.get(key), list) else [])
        if _is_number(value)
    ]
    if bound_values:
        source_coordinate_extent = max(1.0, *(abs(float(value)) for value in bound_values))
    allowed = (
        "id", "from_frame", "to_frame", "layout", "vector_convention",
        "translation_units", "transform_type", "matrix", "inverse_matrix",
        "reflection_allowed", "held_out_count", "round_trip_max",
        "round_trip_tolerance", "conditioning", "evidence",
    )
    for index, raw in enumerate(transforms):
        path = "/transforms/%d" % index
        item = _require_object(
            raw, path, findings,
            required=allowed[:-1],
            allowed=allowed,
        )
        transform_id = _check_id(item.get("id"), _path(path, "id"), findings)
        if transform_id is not None:
            transform_by_id[transform_id] = item
        source = _check_id(item.get("from_frame"), _path(path, "from_frame"), findings)
        target = _check_id(item.get("to_frame"), _path(path, "to_frame"), findings)
        for name, frame in (("from_frame", source), ("to_frame", target)):
            if frame is not None and frame not in frame_ids:
                findings.error("reference.frame", _path(path, name), "frame is not declared in /frames")
        if source is not None and target is not None:
            if source == target:
                findings.error("geometry.self_transform", path, "from_frame and to_frame must differ")
            if (source, target) in pairs:
                findings.error("reference.duplicate_transform", path, "transform pair is duplicated")
            pairs.add((source, target))
            edges.append((source, target))
        if item.get("layout") != "row-major":
            findings.error("transform.layout", _path(path, "layout"), "schema 1.0.0 requires row-major matrices")
        if item.get("vector_convention") != "column-vector":
            findings.error("transform.vector_convention", _path(path, "vector_convention"), "matrix must act on homogeneous column vectors")
        if item.get("translation_units") != "contract-linear-units":
            findings.error("transform.translation_units", _path(path, "translation_units"), "translation must use /units/linear")
        transform_type = item.get("transform_type")
        if transform_type not in ("rigid", "similarity", "affine"):
            findings.error("transform.type", _path(path, "transform_type"), "expected rigid, similarity, or affine")
        matrix_raw = _require_array(item.get("matrix"), _path(path, "matrix"), findings)
        inverse_raw = _require_array(item.get("inverse_matrix"), _path(path, "inverse_matrix"), findings)
        if len(matrix_raw) != 16 or len(inverse_raw) != 16:
            findings.error("transform.matrix_size", path, "matrix and inverse_matrix each need 16 row-major values")
            continue
        matrix_values = [_check_number(value, _path(path, "matrix/%d" % i), findings) for i, value in enumerate(matrix_raw)]
        inverse_values = [_check_number(value, _path(path, "inverse_matrix/%d" % i), findings) for i, value in enumerate(inverse_raw)]
        if any(value is None for value in matrix_values + inverse_values):
            continue
        matrix = [float(value) for value in matrix_values if value is not None]
        inverse = [float(value) for value in inverse_values if value is not None]
        if transform_id is not None and source is not None and target is not None:
            cycle_records.append((transform_id, source, target, matrix, inverse))
        if any(matrix[index] != expected for index, expected in zip((12, 13, 14, 15), (0.0, 0.0, 0.0, 1.0))):
            findings.error("transform.homogeneous_row", _path(path, "matrix"), "last row must be [0, 0, 0, 1]")
        if any(inverse[index] != expected for index, expected in zip((12, 13, 14, 15), (0.0, 0.0, 0.0, 1.0))):
            findings.error("transform.homogeneous_row", _path(path, "inverse_matrix"), "inverse last row must be [0, 0, 0, 1]")
        determinant = _determinant3(matrix)
        rows = [_row3(matrix, row) for row in range(3)]
        norms = [math.sqrt(_dot(row, row)) for row in rows]
        scale = max(norms) if norms else 0.0
        if scale == 0 or abs(determinant) <= 1e-12 * scale**3:
            findings.error("transform.singular", _path(path, "matrix"), "linear transform is singular at its recorded scale")
        reflection_allowed = item.get("reflection_allowed")
        if not isinstance(reflection_allowed, bool):
            findings.error("transform.reflection_flag", _path(path, "reflection_allowed"), "reflection_allowed must be explicit boolean evidence")
        if determinant < 0 and reflection_allowed is not True:
            findings.error("transform.undocumented_reflection", _path(path, "matrix"), "negative determinant requires reflection_allowed=true")
        try:
            forward_cycle = _matrix4_product(matrix, inverse)
            reverse_cycle = _matrix4_product(inverse, matrix)
            inverse_residual = max(_identity_residual(forward_cycle), _identity_residual(reverse_cycle))
        except OverflowError:
            findings.error("transform.overflow", path, "matrix/inverse cycle produced non-finite intermediate values")
            inverse_residual = math.inf
        if inverse_residual > 1e-8:
            findings.error("transform.inverse", _path(path, "inverse_matrix"), "matrix and inverse_matrix do not round-trip to identity")
        held_out = _check_integer(item.get("held_out_count"), _path(path, "held_out_count"), findings, 1)
        round_trip_max = _check_number(item.get("round_trip_max"), _path(path, "round_trip_max"), findings, 0)
        round_trip_tolerance = _check_number(item.get("round_trip_tolerance"), _path(path, "round_trip_tolerance"), findings, 0, exclusive=True)
        if held_out is not None and held_out < 1:
            findings.error("transform.held_out", _path(path, "held_out_count"), "at least one held-out canary is required")
        if round_trip_max is not None and round_trip_tolerance is not None and round_trip_max > round_trip_tolerance:
            findings.error("transform.round_trip", _path(path, "round_trip_max"), "held-out round-trip maximum exceeds tolerance")
        conditioning = _require_object(
            item.get("conditioning"), _path(path, "conditioning"), findings,
            required=("norm", "condition_number", "reciprocal_condition", "evidence"),
            allowed=("norm", "condition_number", "reciprocal_condition", "evidence"),
        )
        if conditioning.get("norm") != "infinity":
            findings.error("transform.conditioning_norm", _path(path, "conditioning/norm"), "conditioning must use the declared infinity norm")
        recorded_condition = _check_number(conditioning.get("condition_number"), _path(path, "conditioning/condition_number"), findings, 1)
        recorded_reciprocal = _check_number(conditioning.get("reciprocal_condition"), _path(path, "conditioning/reciprocal_condition"), findings, 0, exclusive=True)
        computed_condition = _linear_infinity_norm(matrix) * _linear_infinity_norm(inverse)
        if not math.isfinite(computed_condition) or computed_condition > 1e12:
            findings.error("transform.conditioning", _path(path, "conditioning"), "linear transform is too ill-conditioned for reliable handoff")
        if recorded_condition is not None and math.isfinite(computed_condition) and not math.isclose(recorded_condition, computed_condition, rel_tol=1e-6, abs_tol=1e-9):
            findings.error("transform.conditioning", _path(path, "conditioning/condition_number"), "recorded condition number does not match matrix/inverse infinity norm")
        expected_reciprocal = 1.0 / computed_condition if computed_condition > 0 and math.isfinite(computed_condition) else 0.0
        if recorded_reciprocal is not None and not math.isclose(recorded_reciprocal, expected_reciprocal, rel_tol=1e-6, abs_tol=1e-12):
            findings.error("transform.conditioning", _path(path, "conditioning/reciprocal_condition"), "recorded reciprocal condition does not match matrix/inverse")
        if transform_type in ("rigid", "similarity"):
            intended_scale = 1.0 if transform_type == "rigid" else sum(norms) / 3.0
            classification_tolerance = 1e-12
            if source == source_record_frame and round_trip_tolerance is not None:
                classification_tolerance = min(
                    classification_tolerance,
                    round_trip_tolerance / (source_coordinate_extent * max(1.0, intended_scale)),
                )
            norm_tolerance = classification_tolerance * max(1.0, intended_scale)
            orthogonality_tolerance = classification_tolerance * max(1.0, intended_scale * intended_scale)
            if transform_type == "rigid" and any(abs(norm - 1.0) > norm_tolerance for norm in norms):
                findings.error("transform.not_rigid", _path(path, "matrix"), "rigid transform axes must have unit length")
            if transform_type == "similarity" and (intended_scale <= 0 or any(abs(norm - intended_scale) > norm_tolerance for norm in norms)):
                findings.error("transform.not_similarity", _path(path, "matrix"), "similarity transform axes must have one common nonzero scale")
            for first in range(3):
                for second in range(first + 1, 3):
                    if abs(_dot(rows[first], rows[second])) > orthogonality_tolerance:
                        findings.error("transform.non_orthogonal", _path(path, "matrix"), "rigid/similarity axes must be orthogonal")
                        break
        if source in frame_handedness and target in frame_handedness and abs(determinant) >= 1e-12:
            expected_sign = 1 if frame_handedness[source] == frame_handedness[target] else -1
            actual_sign = 1 if determinant > 0 else -1
            if actual_sign != expected_sign and reflection_allowed is not True:
                findings.error("transform.handedness", _path(path, "matrix"), "determinant sign conflicts with declared frame handedness")
    _check_transform_cycles(cycle_records, findings)
    return edges, transform_by_id


def _is_reachable(start: str, target: str, edges: Sequence[Tuple[str, str]]) -> bool:
    graph: Dict[str, Set[str]] = {}
    for left, right in edges:
        graph.setdefault(left, set()).add(right)
        graph.setdefault(right, set()).add(left)
    pending = deque([start])
    seen = {start}
    while pending:
        current = pending.popleft()
        if current == target:
            return True
        for neighbour in graph.get(current, ()):
            if neighbour not in seen:
                seen.add(neighbour)
                pending.append(neighbour)
    return False


def _value_equal(left: Any, right: Any) -> bool:
    if _is_number(left) and _is_number(right):
        return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return all(_value_equal(a, b) for a, b in zip(left, right))
    return left == right


def _json_semantic_equal(left: Any, right: Any) -> bool:
    """Compare decoded JSON values with JSON-number equality and distinct booleans."""

    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if _is_number(left) or _is_number(right):
        return _is_number(left) and _is_number(right) and left == right
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        return (
            isinstance(left, Mapping)
            and isinstance(right, Mapping)
            and set(left) == set(right)
            and all(_json_semantic_equal(left[key], right[key]) for key in left)
        )
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(_json_semantic_equal(a, b) for a, b in zip(left, right))
        )
    return type(left) is type(right) and left == right


def _strictly_less(left: float, right: float) -> bool:
    return left < right and not math.isclose(left, right, rel_tol=1e-12, abs_tol=0.0)


def _strictly_greater(left: float, right: float) -> bool:
    return left > right and not math.isclose(left, right, rel_tol=1e-12, abs_tol=0.0)


def _bounded_unique_reasons(reasons: Iterable[str]) -> List[str]:
    output: List[str] = []
    seen: Set[str] = set()
    for reason in reasons:
        if reason in seen:
            continue
        if len(output) >= MAX_EVIDENCE_REASONS - 1:
            output.append("additional evidence reasons omitted by the hard report budget")
            break
        seen.add(reason)
        output.append(reason)
    return output


def _numbers_close(left: float, right: float) -> bool:
    if left == right:
        return True
    scale = max(abs(left), abs(right))
    return scale > 0 and math.isclose(left, right, rel_tol=1e-12, abs_tol=0.0)


def _fixed_percentile_position(count: int, percentile: float) -> Tuple[int, int, float]:
    integer_percentile = int(percentile)
    if float(integer_percentile) != float(percentile) or not 0 < integer_percentile <= 100:
        raise ValueError("fixed-profile percentile must be an integer in (0, 100]")
    lower, remainder = divmod((count - 1) * integer_percentile, 100)
    return lower, lower + (1 if remainder else 0), remainder / 100.0


def _bounded_moment_maximum(count: int, total: float, lower: float, upper: float) -> Optional[float]:
    """Maximum sum of squares for `count` values in [lower, upper] with `total`."""

    if count == 0:
        return 0.0 if _numbers_close(total, 0.0) else None
    width = upper - lower
    minimum_total = count * lower
    maximum_total = count * upper
    if total < minimum_total and not _numbers_close(total, minimum_total):
        return None
    if total > maximum_total and not _numbers_close(total, maximum_total):
        return None
    if width == 0:
        return count * lower * lower
    extra = min(max(total - minimum_total, 0.0), count * width)
    full = min(count, int(math.floor(extra / width)))
    remainder = extra - full * width
    scale = max(abs(extra), abs(full * width), 1.0)
    if remainder < 0 and abs(remainder) <= scale * 1e-12:
        remainder = 0.0
    if full == count or _numbers_close(remainder, 0.0):
        return math.fsum((full * upper * upper, (count - full) * lower * lower))
    middle = lower + remainder
    return math.fsum(
        (
            full * upper * upper,
            middle * middle,
            (count - full - 1) * lower * lower,
        )
    )


def _check_realizability_certificate(
    raw_certificate: Any,
    path: str,
    count: Optional[int],
    scale: Optional[float],
    threshold: Optional[float],
    within_count: Optional[int],
    within_percent: Optional[float],
    percentile_values: Sequence[Tuple[float, float, str]],
    mean: Optional[float],
    rms: Optional[float],
    findings: Findings,
    mean_path: Optional[str] = None,
    rms_path: Optional[str] = None,
) -> Optional[int]:
    """Validate a sufficient, bounded proof that reported moments are realizable."""

    certificate = _require_object(
        raw_certificate,
        path,
        findings,
        required=("version", "scale", "blocks"),
        allowed=("version", "scale", "blocks"),
    )
    if certificate.get("version") != "normalized-blocks-v1":
        findings.error("validation.certificate_version", _path(path, "version"), "unsupported realizability certificate version")
    certificate_scale = _check_number(certificate.get("scale"), _path(path, "scale"), findings, 0)
    blocks = _require_array(certificate.get("blocks"), _path(path, "blocks"), findings, 1)
    if len(blocks) > MAX_REALIZABILITY_BLOCKS:
        findings.error("validation.certificate_blocks", _path(path, "blocks"), "realizability certificate exceeds the hard 64-block bound")
    if count is None or scale is None or threshold is None:
        return None
    if count > MAX_EXACT_EVIDENCE_INTEGER:
        findings.error("validation.certificate_count", path, "certificate count exceeds the exact binary64 integer range")
        return None
    if certificate_scale is None or not _numbers_close(certificate_scale, scale):
        findings.error("validation.certificate_scale", _path(path, "scale"), "certificate scale must equal the recorded maximum")
        return None

    expected_start = 0
    previous_last = 0.0
    previous_class = "within"
    normalized_sum_parts: List[float] = []
    normalized_square_parts: List[float] = []
    certified_within_count = 0
    index_values: Dict[int, float] = {}
    for block_index, raw_block in enumerate(blocks[:MAX_REALIZABILITY_BLOCKS]):
        block_path = _path(_path(path, "blocks"), block_index)
        block = _require_object(
            raw_block,
            block_path,
            findings,
            required=("start_index", "end_index", "first", "last", "sum", "sum_squares", "threshold_class"),
            allowed=("start_index", "end_index", "first", "last", "sum", "sum_squares", "threshold_class"),
        )
        start = _check_integer(block.get("start_index"), _path(block_path, "start_index"), findings, 0)
        end = _check_integer(block.get("end_index"), _path(block_path, "end_index"), findings, 0)
        first = _check_number(block.get("first"), _path(block_path, "first"), findings, 0)
        last = _check_number(block.get("last"), _path(block_path, "last"), findings, 0)
        block_sum = _check_number(block.get("sum"), _path(block_path, "sum"), findings, 0)
        block_squares = _check_number(block.get("sum_squares"), _path(block_path, "sum_squares"), findings, 0)
        threshold_class = block.get("threshold_class")
        if threshold_class not in ("within", "outside"):
            findings.error("validation.certificate_threshold", _path(block_path, "threshold_class"), "expected within or outside")
        if None in (start, end, first, last, block_sum, block_squares):
            continue
        if not (0 <= block_sum <= MAX_EXACT_EVIDENCE_INTEGER) or not (
            0 <= block_squares <= MAX_EXACT_EVIDENCE_INTEGER
        ):
            findings.error(
                "validation.certificate_precision",
                block_path,
                "normalized block moments must lie in the exact nonnegative binary64 integer range",
            )
            continue
        if start > MAX_EXACT_EVIDENCE_INTEGER or end > MAX_EXACT_EVIDENCE_INTEGER:
            findings.error("validation.certificate_count", block_path, "certificate index exceeds the exact binary64 integer range")
            continue
        if start != expected_start or end < start or end >= count:
            findings.error("validation.certificate_partition", block_path, "certificate blocks must contiguously partition the evaluated index range")
            continue
        block_count = end - start + 1
        expected_start = end + 1
        if first > 1 or last > 1 or _strictly_greater(first, last):
            findings.error("validation.certificate_order", block_path, "normalized block endpoints must satisfy 0 <= first <= last <= 1")
        if (first > 0 and first * first == 0) or (last > 0 and last * last == 0):
            findings.error("validation.certificate_precision", block_path, "normalized endpoint squares underflow the supported certificate precision")
        if block_index and _strictly_greater(previous_last, first):
            findings.error("validation.certificate_order", block_path, "certificate blocks must be globally nondecreasing")
        previous_last = last

        if block_count == 1:
            expected_sum = first
            expected_squares = first * first
            if not _numbers_close(first, last) or not _numbers_close(block_sum, expected_sum) or not _numbers_close(block_squares, expected_squares):
                findings.error("validation.certificate_moments", block_path, "a singleton block must report its one exact endpoint and moment")
        elif block_count == 2:
            expected_sum = first + last
            expected_squares = math.fsum((first * first, last * last))
            if not _numbers_close(block_sum, expected_sum) or not _numbers_close(block_squares, expected_squares):
                findings.error("validation.certificate_moments", block_path, "a two-value block's moments must equal its fixed endpoints")
        else:
            interior_count = block_count - 2
            interior_sum = block_sum - first - last
            interior_squares = block_squares - first * first - last * last
            minimum_interior_sum = interior_count * first
            maximum_interior_sum = interior_count * last
            if (
                interior_sum < minimum_interior_sum and not _numbers_close(interior_sum, minimum_interior_sum)
            ) or (
                interior_sum > maximum_interior_sum and not _numbers_close(interior_sum, maximum_interior_sum)
            ):
                findings.error("validation.certificate_sum", block_path, "block sum is infeasible for its count and fixed endpoints")
            else:
                minimum_squares = (interior_sum / math.sqrt(interior_count)) ** 2
                if interior_sum > 0 and minimum_squares == 0:
                    findings.error("validation.certificate_precision", block_path, "block moments underflow the supported normalized precision")
                maximum_squares = _bounded_moment_maximum(interior_count, interior_sum, first, last)
                if maximum_squares is None:
                    findings.error("validation.certificate_sum", block_path, "block sum is infeasible for its bounded interior")
                elif (
                    interior_squares < minimum_squares and not _numbers_close(interior_squares, minimum_squares)
                ) or (
                    interior_squares > maximum_squares and not _numbers_close(interior_squares, maximum_squares)
                ):
                    findings.error("validation.certificate_moments", block_path, "block sum-of-squares is outside the exact feasible interval")

        normalized_sum_parts.append(block_sum)
        normalized_square_parts.append(block_squares)
        if threshold_class == "within":
            if previous_class == "outside":
                findings.error("validation.certificate_threshold", block_path, "within-threshold blocks cannot follow outside-threshold blocks")
            certified_within_count += block_count
        elif threshold_class == "outside":
            previous_class = "outside"

        if scale == 0:
            if first != 0 or last != 0 or threshold_class != "within":
                findings.error("validation.certificate_threshold", block_path, "a zero-scale certificate must contain only zero within-threshold values")
        else:
            threshold_ratio = threshold / scale
            if threshold_class == "within" and last > threshold_ratio:
                findings.error("validation.certificate_threshold", block_path, "within-threshold block exceeds the declared threshold")
            if threshold_class == "outside" and not first > threshold_ratio:
                findings.error("validation.certificate_threshold", block_path, "outside-threshold block must start strictly above the declared threshold")

        existing_start = index_values.get(start)
        if existing_start is not None and not _numbers_close(existing_start, first):
            findings.error("validation.certificate_order", block_path, "shared block boundary assigns inconsistent order statistics")
        index_values[start] = first
        existing_end = index_values.get(end)
        if existing_end is not None and not _numbers_close(existing_end, last):
            findings.error("validation.certificate_order", block_path, "shared block boundary assigns inconsistent order statistics")
        index_values[end] = last

    if expected_start != count:
        findings.error("validation.certificate_partition", _path(path, "blocks"), "certificate blocks do not cover every evaluated order-statistic index")
    if within_count is not None and certified_within_count != within_count:
        findings.error("validation.certificate_threshold_count", _path(path, "blocks"), "certificate threshold classes do not reproduce the recorded within/exceeding count")
    certified_within_percent = 100.0 * certified_within_count / count
    if within_percent is not None and not _numbers_close(within_percent, certified_within_percent):
        findings.error("validation.certificate_threshold_count", _path(path, "blocks"), "certificate threshold classes do not reproduce the reported within-tolerance percentage")

    for percentile, distance, percentile_path in percentile_values:
        lower, upper, fraction = _fixed_percentile_position(count, percentile)
        if lower not in index_values or upper not in index_values:
            findings.error("validation.certificate_quantile_boundary", percentile_path, "certificate must split at every percentile interpolation endpoint")
            continue
        normalized_distance = index_values[lower] if lower == upper else math.fsum(
            ((1.0 - fraction) * index_values[lower], fraction * index_values[upper])
        )
        if scale == 0:
            matches = distance == 0 and normalized_distance == 0
        else:
            matches = _numbers_close(distance / scale, normalized_distance)
        if not matches:
            findings.error("validation.certificate_percentile", percentile_path, "certificate does not reproduce the reported percentile")

    if scale > 0:
        if count - 1 not in index_values or not _numbers_close(index_values[count - 1], 1.0):
            findings.error("validation.certificate_maximum", path, "certificate final order statistic must normalize to one")
        total_sum = math.fsum(normalized_sum_parts)
        total_squares = math.fsum(normalized_square_parts)
        if mean is not None and not _numbers_close(mean / scale, total_sum / count):
            findings.error("validation.certificate_mean", mean_path or _path(path.rsplit("/", 1)[0], "mean"), "certificate does not reproduce the reported mean")
        if rms is not None and not _numbers_close(rms / scale, math.sqrt(total_squares / count)):
            findings.error("validation.certificate_rms", rms_path or _path(path.rsplit("/", 1)[0], "rms"), "certificate does not reproduce the reported RMS")
    else:
        if mean not in (None, 0.0):
            findings.error("validation.certificate_mean", path, "zero-scale certificate requires zero mean")
        if rms not in (None, 0.0):
            findings.error("validation.certificate_rms", path, "zero-scale certificate requires zero RMS")
    return certified_within_count if expected_start == count else None


def _check_parameter_value(value: Any, path: str, findings: Findings) -> None:
    if _is_number(value):
        return
    if isinstance(value, list) and 2 <= len(value) <= 16:
        for index, item in enumerate(value):
            _check_number(item, _path(path, index), findings)
        return
    findings.error("parameter.value", path, "expected one finite number or an array of 2-16 finite numbers")


def _check_source(value: Any, frame_ids: Set[str], findings: Findings) -> Mapping[str, Any]:
    path = "/source"
    allowed = ("artifact", "canonical_points_sha256", "point_count", "point_record", "frame", "bounds", "units_status", "units_evidence")
    source = _require_object(value, path, findings, required=allowed[:-1], allowed=allowed)
    source_artifact = _check_artifact(source.get("artifact"), "/source/artifact", findings)
    if source_artifact.get("format") not in POINT_EVIDENCE_FORMATS:
        findings.error("source.format", "/source/artifact/format", "source point evidence must use a supported point-cloud format")
    _check_sha(source.get("canonical_points_sha256"), "/source/canonical_points_sha256", findings)
    _check_integer(source.get("point_count"), "/source/point_count", findings, 1)
    if source.get("point_record") not in ("xyz", "xyz-normals", "xyz-rgb", "xyz-normals-rgb"):
        findings.error("source.point_record", "/source/point_record", "unsupported point record declaration")
    frame = _check_id(source.get("frame"), "/source/frame", findings)
    if frame is not None and frame not in frame_ids:
        findings.error("reference.frame", "/source/frame", "source frame is not declared")
    bounds = _check_bounds(source.get("bounds"), "/source/bounds", findings, frame_ids)
    if frame is not None and bounds.get("frame") != frame:
        findings.error("reference.bounds_frame", "/source/bounds/frame", "source bounds must use the source frame")
    if source.get("units_status") not in ("verified", "provisional", "unknown"):
        findings.error("source.units_status", "/source/units_status", "expected verified, provisional, or unknown")
    if source.get("units_status") == "verified" and not source.get("units_evidence"):
        findings.error("source.units_evidence", "/source/units_evidence", "verified units require evidence")
    return source


def _check_samples(
    value: Any,
    source: Mapping[str, Any],
    frame_ids: Set[str],
    transform_edges: Sequence[Tuple[str, str]],
    findings: Findings,
) -> Mapping[str, Any]:
    samples = _require_object(value, "/samples", findings, required=("measurement", "display"), allowed=("measurement", "display"))
    source_artifact = source.get("artifact") if isinstance(source.get("artifact"), Mapping) else {}
    source_hash = source_artifact.get("sha256")
    source_count = source.get("point_count")
    for role in ("measurement", "display"):
        path = "/samples/" + role
        allowed = (
            "role", "artifact", "canonical_points_sha256", "source_sha256", "source_point_count",
            "point_count", "frame", "bounds", "method", "algorithm_version", "seed", "parameters",
        )
        sample = _require_object(samples.get(role), path, findings, required=allowed, allowed=allowed)
        if sample.get("role") != role:
            findings.error("sampling.role", _path(path, "role"), "sample role does not match its contract slot")
        sample_artifact = _check_artifact(sample.get("artifact"), _path(path, "artifact"), findings)
        if sample_artifact.get("format") not in POINT_EVIDENCE_FORMATS:
            findings.error("sampling.format", _path(path, "artifact/format"), "sample point evidence must use a supported point-cloud format")
        _check_sha(sample.get("canonical_points_sha256"), _path(path, "canonical_points_sha256"), findings)
        sample_source_hash = _check_sha(sample.get("source_sha256"), _path(path, "source_sha256"), findings)
        if source_hash is not None and sample_source_hash is not None and sample_source_hash != source_hash:
            findings.error("lineage.source_hash", _path(path, "source_sha256"), "sample does not identify the immutable source artifact")
        sample_source_count = _check_integer(sample.get("source_point_count"), _path(path, "source_point_count"), findings, 1)
        if source_count is not None and sample_source_count is not None and sample_source_count != source_count:
            findings.error("lineage.source_count", _path(path, "source_point_count"), "sample source count differs from /source/point_count")
        point_count = _check_integer(sample.get("point_count"), _path(path, "point_count"), findings, 1)
        if point_count is not None and sample_source_count is not None and point_count > sample_source_count:
            findings.error("sampling.count", _path(path, "point_count"), "sample cannot contain more points than its source")
        frame = _check_id(sample.get("frame"), _path(path, "frame"), findings)
        if frame is not None and frame not in frame_ids:
            findings.error("reference.frame", _path(path, "frame"), "sample frame is not declared")
        source_frame = source.get("frame")
        if isinstance(source_frame, str) and frame is not None and not _is_reachable(source_frame, frame, transform_edges):
            findings.error("reference.transform_path", _path(path, "frame"), "sample frame is not connected to the immutable source frame")
        bounds = _check_bounds(sample.get("bounds"), _path(path, "bounds"), findings, frame_ids)
        if frame is not None and bounds.get("frame") != frame:
            findings.error("reference.bounds_frame", _path(path, "bounds/frame"), "sample bounds must use the sample frame")
        source_bounds = source.get("bounds") if isinstance(source.get("bounds"), Mapping) else {}
        if frame == source.get("frame"):
            sample_lower, sample_upper = bounds.get("min"), bounds.get("max")
            source_lower, source_upper = source_bounds.get("min"), source_bounds.get("max")
            if all(
                isinstance(vector, list)
                and len(vector) == 3
                and all(_is_number(coordinate) for coordinate in vector)
                for vector in (sample_lower, sample_upper, source_lower, source_upper)
            ):
                if any(sample_lower[axis] < source_lower[axis] or sample_upper[axis] > source_upper[axis] for axis in range(3)):
                    findings.error("sampling.bounds_containment", _path(path, "bounds"), "same-frame sample bounds must be contained by source bounds")
        method = sample.get("method")
        if method not in ("full", "hash-rank", "masked-hash-rank", "voxel-first"):
            findings.error("sampling.method", _path(path, "method"), "unsupported deterministic sampling method")
        if not isinstance(sample.get("algorithm_version"), str) or ALGORITHM_VERSION_RE.fullmatch(sample.get("algorithm_version", "")) is None:
            findings.error("sampling.algorithm_version", _path(path, "algorithm_version"), "algorithm version must be a short portable token")
        _check_integer(sample.get("seed"), _path(path, "seed"), findings, 0)
        params = _require_object(sample.get("parameters"), _path(path, "parameters"), findings, allowed=("target_count", "voxel_size", "eligible_count", "mask_sha256"))
        if method == "full":
            if point_count is not None and sample_source_count is not None and point_count != sample_source_count:
                findings.error("sampling.full_count", _path(path, "point_count"), "full sample must preserve every source point")
            if frame != source.get("frame"):
                findings.error("sampling.full_frame", _path(path, "frame"), "full samples must remain in the source frame")
            if sample.get("canonical_points_sha256") != source.get("canonical_points_sha256"):
                findings.error("sampling.full_order", _path(path, "canonical_points_sha256"), "same-frame full samples must preserve source order and canonical hash")
            if bounds.get("min") != source_bounds.get("min") or bounds.get("max") != source_bounds.get("max"):
                findings.error("sampling.full_bounds", _path(path, "bounds"), "same-frame full sample bounds must exactly equal source bounds")
            if params:
                findings.error("sampling.full_parameters", _path(path, "parameters"), "unmasked full samples must not carry selection parameters")
        if method in ("hash-rank", "masked-hash-rank"):
            target_count = _check_integer(params.get("target_count"), _path(path, "parameters/target_count"), findings, 1)
            if target_count is not None and point_count is not None and target_count < point_count:
                findings.error("sampling.target_count", _path(path, "parameters/target_count"), "target_count cannot be below the recorded sample count")
            if method == "hash-rank" and target_count is not None and point_count is not None and sample_source_count is not None:
                expected_count = min(target_count, sample_source_count)
                if point_count != expected_count:
                    findings.error("sampling.algorithm_count", _path(path, "point_count"), "hash-rank point count must equal min(target_count, source_point_count)")
                if target_count >= sample_source_count:
                    findings.error("sampling.full_method", _path(path, "method"), "an unmasked sample retaining every source point must use full and preserve source order")
        if method == "masked-hash-rank":
            eligible_count = _check_integer(params.get("eligible_count"), _path(path, "parameters/eligible_count"), findings, 1)
            _check_sha(params.get("mask_sha256"), _path(path, "parameters/mask_sha256"), findings)
            if eligible_count is not None and sample_source_count is not None and eligible_count > sample_source_count:
                findings.error("sampling.eligible_count", _path(path, "parameters/eligible_count"), "eligible point count cannot exceed source point count")
            if eligible_count is not None and point_count is not None and point_count > eligible_count:
                findings.error("sampling.eligible_count", _path(path, "point_count"), "masked sample cannot exceed eligible point count")
            if target_count is not None and eligible_count is not None and point_count is not None:
                expected_count = min(target_count, eligible_count)
                if point_count != expected_count:
                    findings.error("sampling.algorithm_count", _path(path, "point_count"), "masked-hash-rank point count must equal min(target_count, eligible_count)")
        elif "mask_sha256" in params or "eligible_count" in params:
            findings.error("sampling.mask_method", _path(path, "method"), "masked derivation metadata requires masked-hash-rank")
        if method == "voxel-first":
            _check_number(params.get("voxel_size"), _path(path, "parameters/voxel_size"), findings, 0, exclusive=True)
    measurement = samples.get("measurement") if isinstance(samples.get("measurement"), Mapping) else {}
    display = samples.get("display") if isinstance(samples.get("display"), Mapping) else {}
    measurement_artifact = measurement.get("artifact") if isinstance(measurement.get("artifact"), Mapping) else {}
    display_artifact = display.get("artifact") if isinstance(display.get("artifact"), Mapping) else {}
    if measurement_artifact.get("sha256") == display_artifact.get("sha256") and measurement.get("point_count") != display.get("point_count"):
        findings.error("sampling.role_identity", "/samples/display/artifact/sha256", "different point sets cannot share one artifact hash")
    return samples


def _kernel_family(value: Any) -> str:
    """Return a conservative kernel-family key without treating versions as families."""

    normalized = re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()
    tokens = normalized.split()
    compact = "".join(tokens)
    if "opencascade" in compact or "occt" in tokens:
        return "occt"
    if "parasolid" in compact:
        return "parasolid"
    if "shapemanager" in compact or "autodeskshapemanager" in compact:
        return "autodesk-shapemanager"
    if "acis" in tokens or "spatialacis" in compact:
        return "acis"
    if "cgm" in tokens:
        return "cgm"
    if "granite" in tokens:
        return "granite"
    if "opennurbs" in compact:
        return "opennurbs"
    if "blender" in tokens and ("mesh" in tokens or "bmesh" in tokens):
        return "blender-mesh"
    if "oda" in tokens or "opendesignalliance" in compact:
        return "oda"
    return ""


def _tool_identity(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _check_authority(value: Any, frame_ids: Set[str], findings: Findings) -> Mapping[str, Any]:
    path = "/authority"
    allowed = (
        "kind", "artifact", "validation_sample", "producer", "replay_source_sha256",
        "independent_reopen", "brep_validation", "fusion_validation", "blend_validation",
        "operation_chain_validation", "mesh_validation",
    )
    authority = _require_object(
        value, path, findings,
        required=("kind", "artifact", "validation_sample", "producer", "replay_source_sha256"),
        allowed=allowed,
    )
    kind = authority.get("kind")
    kinds = ("step_brep", "dwg_3dsolid", "fusion_f3d", "blend_scene", "occt_operation_chain", "procedural_mesh")
    if kind not in kinds:
        findings.error("authority.kind", "/authority/kind", "unsupported modelling authority")
    artifact = _check_artifact(authority.get("artifact"), "/authority/artifact", findings)
    validation_sample = _require_object(
        authority.get("validation_sample"), "/authority/validation_sample", findings,
        required=("artifact", "point_count", "frame", "bounds", "derivation"),
        allowed=("artifact", "point_count", "frame", "bounds", "derivation"),
    )
    validation_sample_artifact = _check_artifact(validation_sample.get("artifact"), "/authority/validation_sample/artifact", findings)
    if validation_sample_artifact.get("format") not in POINT_EVIDENCE_FORMATS:
        findings.error("authority.sample_format", "/authority/validation_sample/artifact/format", "authority validation sample must use a supported point-cloud format")
    _check_integer(validation_sample.get("point_count"), "/authority/validation_sample/point_count", findings, 1)
    sample_frame = _check_id(validation_sample.get("frame"), "/authority/validation_sample/frame", findings)
    if sample_frame is not None and sample_frame not in frame_ids:
        findings.error("reference.frame", "/authority/validation_sample/frame", "authority sample frame is not declared")
    sample_bounds = _check_bounds(validation_sample.get("bounds"), "/authority/validation_sample/bounds", findings, frame_ids)
    if sample_frame is not None and sample_bounds.get("frame") != sample_frame:
        findings.error("reference.bounds_frame", "/authority/validation_sample/bounds/frame", "authority sample bounds must use its frame")
    derivation = _require_object(
        validation_sample.get("derivation"), "/authority/validation_sample/derivation", findings,
        required=("method", "source_authority_sha256", "algorithm_version", "parameters_sha256"),
        allowed=("method", "source_authority_sha256", "algorithm_version", "parameters_sha256"),
    )
    if derivation.get("method") not in ("surface-tessellation", "analytic-surface-sampling", "mesh-vertices", "evaluated-copy"):
        findings.error("authority.sample_method", "/authority/validation_sample/derivation/method", "unsupported authority-sample derivation")
    if not isinstance(derivation.get("algorithm_version"), str) or ALGORITHM_VERSION_RE.fullmatch(derivation.get("algorithm_version", "")) is None:
        findings.error("authority.algorithm_version", "/authority/validation_sample/derivation/algorithm_version", "algorithm version must be a short portable token")
    derivation_hash = _check_sha(derivation.get("source_authority_sha256"), "/authority/validation_sample/derivation/source_authority_sha256", findings)
    if derivation_hash is not None and artifact.get("sha256") is not None and derivation_hash != artifact.get("sha256"):
        findings.error("lineage.authority_sample", "/authority/validation_sample/derivation/source_authority_sha256", "authority sample must identify the declared authority artifact")
    _check_sha(derivation.get("parameters_sha256"), "/authority/validation_sample/derivation/parameters_sha256", findings)
    _check_sha(authority.get("replay_source_sha256"), "/authority/replay_source_sha256", findings)
    producer = _require_object(
        authority.get("producer"), "/authority/producer", findings,
        required=("tool", "tool_version", "kernel"),
        allowed=("tool", "tool_version", "kernel"),
    )
    expected_formats = {
        "step_brep": {"step", "stp"},
        "dwg_3dsolid": {"dwg"},
        "fusion_f3d": {"f3d"},
        "blend_scene": {"blend"},
        "occt_operation_chain": {"json", "occt-chain"},
        "procedural_mesh": {"stl", "3mf", "obj", "ply"},
    }
    if kind in expected_formats and artifact.get("format") not in expected_formats[kind]:
        findings.error("authority.format", "/authority/artifact/format", "artifact format is incompatible with authority kind %s" % kind)
    reopen_required = kind in kinds
    reopen = _require_object(
        authority.get("independent_reopen"),
        "/authority/independent_reopen",
        findings,
        required=("passed", "tool", "tool_version", "kernel", "validation_tier") if reopen_required else (),
        allowed=("passed", "tool", "tool_version", "kernel", "validation_tier", "notes"),
    )
    if reopen_required and reopen.get("passed") is not True:
        findings.error("authority.reopen", "/authority/independent_reopen/passed", "authority artifact must pass its declared fresh or independent reopen gate")
    producer_tool = _tool_identity(producer.get("tool", ""))
    producer_kernel = _kernel_family(producer.get("kernel", ""))
    reopen_tool = _tool_identity(reopen.get("tool", ""))
    reopen_kernel = _kernel_family(reopen.get("kernel", ""))
    tier = reopen.get("validation_tier")
    if tier not in ("same-kernel-fresh-process", "alternate-importer", "cross-kernel"):
        findings.error("authority.validation_tier", "/authority/independent_reopen/validation_tier", "unknown reopen validation tier")
    elif not producer_kernel or not reopen_kernel:
        findings.error("authority.kernel_identity", "/authority/independent_reopen/kernel", "validation tiers require producer and reopen kernels from recognized canonical families")
    elif tier == "same-kernel-fresh-process":
        if producer_kernel and reopen_kernel and producer_kernel != reopen_kernel:
            findings.error("authority.kernel_lineage", "/authority/independent_reopen/kernel", "same-kernel tier requires matching producer and reopen kernels")
        if kind in ("step_brep", "dwg_3dsolid", "fusion_f3d"):
            findings.warning("authority.same_kernel_only", "/authority/independent_reopen/validation_tier", "same-kernel reopen is useful but does not establish alternate-importer or cross-kernel portability")
    elif tier == "alternate-importer":
        if producer_kernel and reopen_kernel and producer_kernel != reopen_kernel:
            findings.error("authority.kernel_lineage", "/authority/independent_reopen/kernel", "alternate-importer tier keeps the producer kernel family")
        if producer_tool and reopen_tool and producer_tool == reopen_tool:
            findings.error("authority.importer_lineage", "/authority/independent_reopen/tool", "alternate-importer tier requires a different importing application")
    elif tier == "cross-kernel":
        if producer_kernel and reopen_kernel and producer_kernel == reopen_kernel:
            findings.error("authority.kernel_lineage", "/authority/independent_reopen/kernel", "cross-kernel tier requires a different kernel family")
    if kind in ("step_brep", "dwg_3dsolid", "fusion_f3d"):
        brep = _require_object(
            authority.get("brep_validation"), "/authority/brep_validation", findings,
            required=("valid_solid", "solid_count", "volume", "unsupported_freeform_surface_count"),
            allowed=("valid_solid", "solid_count", "volume", "unsupported_freeform_surface_count", "surface_classes"),
        )
        if brep.get("valid_solid") is not True:
            findings.error("authority.valid_solid", "/authority/brep_validation/valid_solid", "B-rep authority must contain a valid solid")
        _check_integer(brep.get("solid_count"), "/authority/brep_validation/solid_count", findings, 1)
        _check_number(brep.get("volume"), "/authority/brep_validation/volume", findings, 0, exclusive=True)
        _check_integer(brep.get("unsupported_freeform_surface_count"), "/authority/brep_validation/unsupported_freeform_surface_count", findings, 0)
    if kind == "fusion_f3d":
        fusion = _require_object(
            authority.get("fusion_validation"), "/authority/fusion_validation", findings,
            required=("fresh_source_rebuild", "edit_restore_probe", "source_outputs_fresh", "feature_count", "body_count", "build_warning_count"),
            allowed=("fresh_source_rebuild", "edit_restore_probe", "source_outputs_fresh", "feature_count", "body_count", "build_warning_count"),
        )
        if (fusion.get("fresh_source_rebuild") is not True
                or fusion.get("edit_restore_probe") is not True
                or fusion.get("source_outputs_fresh") is not True):
            findings.error("authority.fusion_gate", "/authority/fusion_validation", "native Fusion authority must pass fresh rebuild, edit-restore, and output-freshness gates")
        _check_integer(fusion.get("feature_count"), "/authority/fusion_validation/feature_count", findings, 1)
        _check_integer(fusion.get("body_count"), "/authority/fusion_validation/body_count", findings, 1)
        warning_count = _check_integer(fusion.get("build_warning_count"), "/authority/fusion_validation/build_warning_count", findings, 0)
        if warning_count not in (None, 0):
            findings.error("authority.fusion_warnings", "/authority/fusion_validation/build_warning_count", "native Fusion build must have zero recorded warnings")
    elif kind == "blend_scene":
        blend = _require_object(
            authority.get("blend_validation"), "/authority/blend_validation", findings,
            required=("fresh_process_reopen", "native_object_count", "evaluation_canary"),
            allowed=("fresh_process_reopen", "native_object_count", "evaluation_canary"),
        )
        if blend.get("fresh_process_reopen") is not True or blend.get("evaluation_canary") is not True:
            findings.error("authority.blend_gate", "/authority/blend_validation", "native scene must reopen and pass an evaluated-copy canary")
        _check_integer(blend.get("native_object_count"), "/authority/blend_validation/native_object_count", findings, 1)
    elif kind == "occt_operation_chain":
        chain = _require_object(
            authority.get("operation_chain_validation"), "/authority/operation_chain_validation", findings,
            required=("operation_chain_sha256", "deterministic_replay", "replay_count"),
            allowed=("operation_chain_sha256", "deterministic_replay", "replay_count"),
        )
        _check_sha(chain.get("operation_chain_sha256"), "/authority/operation_chain_validation/operation_chain_sha256", findings)
        if chain.get("deterministic_replay") is not True:
            findings.error("authority.replay", "/authority/operation_chain_validation/deterministic_replay", "operation chain must replay deterministically")
        _check_integer(chain.get("replay_count"), "/authority/operation_chain_validation/replay_count", findings, 2)
    elif kind == "procedural_mesh":
        mesh = _require_object(
            authority.get("mesh_validation"), "/authority/mesh_validation", findings,
            required=("triangle_count", "degenerate_triangle_count", "boundary_edge_count", "non_manifold_edge_count", "consistent_winding"),
            allowed=("triangle_count", "degenerate_triangle_count", "boundary_edge_count", "non_manifold_edge_count", "consistent_winding"),
        )
        _check_integer(mesh.get("triangle_count"), "/authority/mesh_validation/triangle_count", findings, 1)
        for key in ("degenerate_triangle_count", "boundary_edge_count", "non_manifold_edge_count"):
            count = _check_integer(mesh.get(key), _path("/authority/mesh_validation", key), findings, 0)
            if count not in (None, 0):
                findings.error("authority.mesh_structure", _path("/authority/mesh_validation", key), "print authority requires zero %s" % key)
        if mesh.get("consistent_winding") is not True:
            findings.error("authority.mesh_winding", "/authority/mesh_validation/consistent_winding", "mesh winding must be consistent")
    return authority


def _check_components(
    value: Any,
    authority: Mapping[str, Any],
    frame_ids: Set[str],
    source_frame: Optional[str],
    transform_edges: Sequence[Tuple[str, str]],
    findings: Findings,
) -> Tuple[Sequence[Any], Set[str]]:
    components = _require_array(value, "/components", findings, 1)
    if len(components) != 1:
        findings.error("component.contract_scope", "/components", "feature-contract v1 accepts exactly one independently validated component")
    component_ids = _check_unique_ids(components, "/components", findings)
    artifact = authority.get("artifact") if isinstance(authority.get("artifact"), Mapping) else {}
    authority_hash = artifact.get("sha256")
    allowed = ("id", "frame", "authority_sha256", "primitive_chain", "included_features", "excluded_features")
    for index, raw in enumerate(components):
        path = "/components/%d" % index
        item = _require_object(raw, path, findings, required=allowed, allowed=allowed)
        frame = _check_id(item.get("frame"), _path(path, "frame"), findings)
        if frame is not None and frame not in frame_ids:
            findings.error("reference.frame", _path(path, "frame"), "component frame is not declared")
        if source_frame and frame and not _is_reachable(source_frame, frame, transform_edges):
            findings.error("reference.transform_path", _path(path, "frame"), "no transform path connects source evidence to this component frame")
        component_hash = _check_sha(item.get("authority_sha256"), _path(path, "authority_sha256"), findings)
        if authority_hash is not None and component_hash is not None and component_hash != authority_hash:
            findings.error("lineage.authority_hash", _path(path, "authority_sha256"), "component does not identify the declared authority artifact")
        chain = _require_array(item.get("primitive_chain"), _path(path, "primitive_chain"), findings, 1)
        for chain_index, step in enumerate(chain):
            if not isinstance(step, str) or not step.strip():
                findings.error("component.primitive", _path(path, "primitive_chain/%d" % chain_index), "primitive-chain step must be nonempty text")
        included = _require_array(item.get("included_features"), _path(path, "included_features"), findings)
        excluded = _require_array(item.get("excluded_features"), _path(path, "excluded_features"), findings)
        included_ids = {_check_id(feature, _path(path, "included_features/%d" % i), findings) for i, feature in enumerate(included)}
        excluded_ids = {_check_id(feature, _path(path, "excluded_features/%d" % i), findings) for i, feature in enumerate(excluded)}
        overlap = (included_ids - {None}) & (excluded_ids - {None})
        if overlap:
            findings.error("component.feature_overlap", path, "features cannot be both included and excluded: %s" % ", ".join(sorted(overlap)))
    return components, component_ids


def _check_masks(
    value: Any,
    frame_ids: Set[str],
    components: Sequence[Any],
    component_ids: Set[str],
    findings: Findings,
) -> Tuple[Sequence[Any], Set[str]]:
    masks = _require_array(value, "/masks", findings, 1)
    mask_ids = _check_unique_ids(masks, "/masks", findings)
    component_features = {
        item.get("id"): set(item.get("included_features", []))
        for item in components
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    allowed = ("id", "role", "component_id", "feature_id", "frame", "definition_sha256", "definition")
    for index, raw in enumerate(masks):
        path = "/masks/%d" % index
        item = _require_object(raw, path, findings, required=("id", "role", "frame", "definition_sha256", "definition"), allowed=allowed)
        if item.get("role") not in ("global", "critical-feature", "observed-surface", "fit"):
            findings.error("mask.role", _path(path, "role"), "unsupported mask role")
        frame = _check_id(item.get("frame"), _path(path, "frame"), findings)
        if frame is not None and frame not in frame_ids:
            findings.error("reference.frame", _path(path, "frame"), "mask frame is not declared")
        component = item.get("component_id")
        if component is not None and component not in component_ids:
            findings.error("reference.component", _path(path, "component_id"), "mask component is not declared")
        role = item.get("role")
        feature = item.get("feature_id")
        if role in ("global", "critical-feature") and component is None:
            findings.error("mask.component", _path(path, "component_id"), "acceptance masks require an explicit component")
        if role == "critical-feature":
            checked_feature = _check_id(feature, _path(path, "feature_id"), findings)
            if component in component_features and checked_feature not in component_features[component]:
                findings.error("reference.feature", _path(path, "feature_id"), "critical mask feature is not included by its component")
        elif feature is not None:
            findings.error("mask.feature_scope", _path(path, "feature_id"), "feature_id is reserved for critical-feature masks")
        definition_hash = _check_sha(item.get("definition_sha256"), _path(path, "definition_sha256"), findings)
        definition = _require_object(item.get("definition"), _path(path, "definition"), findings)
        definition_type = definition.get("type")
        if definition_type == "aabb":
            _require_object(definition, _path(path, "definition"), findings, required=("type", "min", "max"), allowed=("type", "min", "max"))
            lower = _check_vector3(definition.get("min"), _path(path, "definition/min"), findings)
            upper = _check_vector3(definition.get("max"), _path(path, "definition/max"), findings)
            if lower and upper and any(a > b for a, b in zip(lower, upper)):
                findings.error("geometry.bounds_order", _path(path, "definition"), "AABB mask minimum must not exceed maximum")
        elif definition_type == "sphere":
            _require_object(definition, _path(path, "definition"), findings, required=("type", "center", "radius"), allowed=("type", "center", "radius"))
            _check_vector3(definition.get("center"), _path(path, "definition/center"), findings)
            _check_number(definition.get("radius"), _path(path, "definition/radius"), findings, 0, exclusive=True)
        elif definition_type == "external":
            _require_object(definition, _path(path, "definition"), findings, required=("type", "artifact_sha256"), allowed=("type", "artifact_sha256"))
            _check_sha(definition.get("artifact_sha256"), _path(path, "definition/artifact_sha256"), findings)
        else:
            findings.error("mask.definition", _path(path, "definition/type"), "expected aabb, sphere, or external")
        if definition_hash is not None:
            actual_hash = canonical_json_sha256(definition)
            if definition_hash != actual_hash:
                findings.error("lineage.mask_hash", _path(path, "definition_sha256"), "digest does not match canonical JSON mask definition")
    global_scopes = [
        (item.get("frame"), item.get("component_id"), item.get("definition"))
        for item in masks
        if isinstance(item, Mapping) and item.get("role") == "global"
    ]
    for index, item in enumerate(masks):
        if not isinstance(item, Mapping) or item.get("role") != "critical-feature":
            continue
        if any(
            item.get("frame") == frame
            and item.get("component_id") == component
            and _json_semantic_equal(item.get("definition"), definition)
            for frame, component, definition in global_scopes
        ):
            findings.error(
                "mask.critical_scope",
                "/masks/%d/definition_sha256" % index,
                "critical-feature mask geometry must be distinct from its component's global mask",
            )
    return masks, mask_ids


def _check_parameters(
    value: Any,
    component_ids: Set[str],
    masks: Sequence[Any],
    mask_ids: Set[str],
    linear_unit: Any,
    angular_unit: Any,
    findings: Findings,
) -> None:
    parameters = _require_array(value, "/parameters", findings)
    _check_unique_ids(parameters, "/parameters", findings)
    mask_by_id = {
        item.get("id"): item for item in masks
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    allowed = ("id", "component_id", "unit", "raw_fit", "regularized", "fit_uncertainty", "regularization_reason", "evidence_mask_ids")
    for index, raw in enumerate(parameters):
        path = "/parameters/%d" % index
        item = _require_object(
            raw, path, findings,
            required=("id", "component_id", "unit", "raw_fit", "regularized", "fit_uncertainty", "evidence_mask_ids"),
            allowed=allowed,
        )
        if item.get("component_id") not in component_ids:
            findings.error("reference.component", _path(path, "component_id"), "parameter component is not declared")
        unit = item.get("unit")
        valid_units = ("mm", "cm", "m", "in", "deg", "rad", "ratio", "count", "none")
        if unit not in valid_units:
            findings.error("parameter.unit", _path(path, "unit"), "unsupported parameter unit")
        if unit in ("mm", "cm", "m", "in") and unit != linear_unit:
            findings.error("parameter.unit_conversion", _path(path, "unit"), "length parameters must use /units/linear; store conversions before contract creation")
        if unit in ("deg", "rad") and unit != angular_unit:
            findings.error("parameter.unit_conversion", _path(path, "unit"), "angle parameters must use /units/angular")
        _check_parameter_value(item.get("raw_fit"), _path(path, "raw_fit"), findings)
        _check_parameter_value(item.get("regularized"), _path(path, "regularized"), findings)
        _check_number(item.get("fit_uncertainty"), _path(path, "fit_uncertainty"), findings, 0)
        if not _value_equal(item.get("raw_fit"), item.get("regularized")) and not item.get("regularization_reason"):
            findings.error("parameter.regularization_reason", _path(path, "regularization_reason"), "changed fitted values require a design-intent rationale")
        evidence_masks = _require_array(item.get("evidence_mask_ids"), _path(path, "evidence_mask_ids"), findings, 1)
        for mask_index, mask_id in enumerate(evidence_masks):
            if mask_id not in mask_ids:
                findings.error("reference.mask", _path(path, "evidence_mask_ids/%d" % mask_index), "parameter evidence mask is not declared")
            elif mask_by_id.get(mask_id, {}).get("component_id") != item.get("component_id"):
                findings.error("lineage.parameter_mask_component", _path(path, "evidence_mask_ids/%d" % mask_index), "parameter evidence mask must belong to the parameter component")


def _check_exclusions(
    value: Any,
    mask_ids: Set[str],
    findings: Findings,
) -> Tuple[Sequence[Any], Set[str]]:
    exclusions = _require_array(value, "/exclusions", findings)
    exclusion_ids = _check_unique_ids(exclusions, "/exclusions", findings)
    allowed = ("id", "mask_id", "reason", "rationale", "approved")
    reasons = ("unobserved-closure", "scanner-occlusion", "fixture", "separate-component", "documented-outlier")
    for index, raw in enumerate(exclusions):
        path = "/exclusions/%d" % index
        item = _require_object(raw, path, findings, required=allowed, allowed=allowed)
        if item.get("mask_id") not in mask_ids:
            findings.error("reference.mask", _path(path, "mask_id"), "exclusion mask is not declared")
        if item.get("reason") not in reasons:
            findings.error("exclusion.reason", _path(path, "reason"), "unsupported exclusion reason")
        if not isinstance(item.get("rationale"), str) or not item.get("rationale", "").strip():
            findings.error("exclusion.rationale", _path(path, "rationale"), "exclusion requires a nonempty rationale")
        if item.get("approved") is not True:
            findings.error("exclusion.approval", _path(path, "approved"), "unapproved exclusions cannot be used in acceptance metrics")
    return exclusions, exclusion_ids


def _check_uncertainty(value: Any, linear_unit: Any, findings: Findings) -> Tuple[Optional[float], Set[str]]:
    path = "/uncertainty"
    allowed = ("unit", "model", "confidence_level", "components", "combined_standard_uncertainty", "coverage_factor", "expanded_uncertainty")
    uncertainty = _require_object(value, path, findings, required=allowed, allowed=allowed)
    if uncertainty.get("unit") != linear_unit:
        findings.error("uncertainty.unit", "/uncertainty/unit", "uncertainty must use /units/linear")
    model = uncertainty.get("model")
    if model not in ("rss-independent", "worst-case", "reported-only"):
        findings.error("uncertainty.model", "/uncertainty/model", "unsupported uncertainty model")
    confidence = _check_number(uncertainty.get("confidence_level"), "/uncertainty/confidence_level", findings, 0, exclusive=True)
    if confidence is not None and confidence > 1:
        findings.error("uncertainty.confidence", "/uncertainty/confidence_level", "confidence level cannot exceed 1")
    components = _require_array(uncertainty.get("components"), "/uncertainty/components", findings, 1)
    _check_unique_ids(components, "/uncertainty/components", findings)
    values: List[float] = []
    kinds: Set[str] = set()
    for index, raw in enumerate(components):
        component_path = "/uncertainty/components/%d" % index
        item = _require_object(raw, component_path, findings, required=("id", "kind", "standard_uncertainty", "evidence"), allowed=("id", "kind", "standard_uncertainty", "evidence"))
        if item.get("kind") not in ("scanner", "registration", "scale", "segmentation", "model", "fit", "sampling"):
            findings.error("uncertainty.kind", _path(component_path, "kind"), "unsupported uncertainty component")
        elif isinstance(item.get("kind"), str):
            kinds.add(item["kind"])
        number = _check_number(item.get("standard_uncertainty"), _path(component_path, "standard_uncertainty"), findings, 0)
        if number is not None:
            values.append(number)
        if not isinstance(item.get("evidence"), str) or not item.get("evidence", "").strip():
            findings.error("uncertainty.evidence", _path(component_path, "evidence"), "uncertainty component needs evidence")
    combined = _check_number(uncertainty.get("combined_standard_uncertainty"), "/uncertainty/combined_standard_uncertainty", findings, 0)
    factor = _check_number(uncertainty.get("coverage_factor"), "/uncertainty/coverage_factor", findings, 1)
    expanded = _check_number(uncertainty.get("expanded_uncertainty"), "/uncertainty/expanded_uncertainty", findings, 0)
    if combined is not None and values and model != "reported-only":
        try:
            expected = math.hypot(*values) if model == "rss-independent" else math.fsum(values)
        except OverflowError:
            expected = math.inf
        if not math.isfinite(expected):
            findings.error("uncertainty.combination", "/uncertainty/components", "uncertainty combination overflows the finite contract range")
        elif not math.isclose(combined, expected, rel_tol=1e-6, abs_tol=0.0):
            findings.error("uncertainty.combination", "/uncertainty/combined_standard_uncertainty", "value does not match the declared %s combination (expected %.12g)" % (model, expected))
    if combined is not None and factor is not None and expanded is not None:
        expected_expanded = combined * factor
        if not math.isfinite(expected_expanded):
            findings.error("uncertainty.expansion", "/uncertainty/expanded_uncertainty", "uncertainty expansion overflows the finite contract range")
        elif not math.isclose(expanded, expected_expanded, rel_tol=1e-6, abs_tol=0.0):
            findings.error("uncertainty.expansion", "/uncertainty/expanded_uncertainty", "expanded uncertainty must equal combined uncertainty times coverage factor")
    return expanded, kinds


def _ordered_chain_reaches(
    start: str,
    target: str,
    transform_ids: Sequence[Any],
    transform_by_id: Mapping[str, Mapping[str, Any]],
    path: str,
    findings: Findings,
) -> bool:
    current = start
    for index, transform_id in enumerate(transform_ids):
        transform = transform_by_id.get(transform_id) if isinstance(transform_id, str) else None
        if transform is None:
            findings.error("reference.transform", _path(path, index), "comparison transform is not declared")
            return False
        if transform.get("from_frame") != current:
            findings.error("reference.transform_order", _path(path, index), "ordered transform chain does not begin at the current artifact frame")
            return False
        current = transform.get("to_frame")
    if current != target:
        findings.error("reference.transform_order", path, "ordered transform chain does not terminate in comparison_frame")
        return False
    return True


def _check_validation(
    value: Any,
    source: Mapping[str, Any],
    samples: Mapping[str, Any],
    authority: Mapping[str, Any],
    components: Sequence[Any],
    component_ids: Set[str],
    masks: Sequence[Any],
    mask_ids: Set[str],
    exclusions: Sequence[Any],
    exclusion_ids: Set[str],
    expanded_uncertainty: Optional[float],
    uncertainty_model: Any,
    uncertainty_kinds: Set[str],
    frame_ids: Set[str],
    transform_by_id: Mapping[str, Mapping[str, Any]],
    findings: Findings,
) -> Tuple[str, List[Mapping[str, Any]]]:
    validation = _require_object(value, "/validation", findings, required=("requirements", "results"), allowed=("requirements", "results"))
    requirements = _require_object(
        validation.get("requirements"), "/validation/requirements", findings,
        required=("directions", "required_percentiles", "max_peak_memory_mib", "critical_component_ids"),
        allowed=("directions", "required_percentiles", "max_peak_memory_mib", "critical_component_ids"),
    )
    directions = _require_array(requirements.get("directions"), "/validation/requirements/directions", findings, 2)
    required_directions = {"cloud-to-authority", "authority-to-cloud"}
    if set(directions) != required_directions:
        findings.error("validation.directions", "/validation/requirements/directions", "both validation directions are required exactly once")
    percentile_values = _require_array(requirements.get("required_percentiles"), "/validation/requirements/required_percentiles", findings, 1)
    required_percentiles: Set[float] = set()
    for index, percentile in enumerate(percentile_values):
        number = _check_number(percentile, "/validation/requirements/required_percentiles/%d" % index, findings, 0, exclusive=True)
        if number is not None:
            if number > 100:
                findings.error("validation.percentile", "/validation/requirements/required_percentiles/%d" % index, "percentile cannot exceed 100")
            if number in required_percentiles:
                findings.error("validation.percentile_duplicate", "/validation/requirements/required_percentiles/%d" % index, "required percentile is duplicated")
            required_percentiles.add(number)
    invariant_percentiles = set(REQUIRED_PERCENTILE_PROFILE)
    if tuple(float(value) for value in percentile_values if _is_number(value)) != REQUIRED_PERCENTILE_PROFILE:
        findings.error(
            "validation.required_percentile_profile",
            "/validation/requirements/required_percentiles",
            "contract v1 requires exactly P50, P95, P98, and P99 in ascending order",
        )
    memory_budget = _check_number(requirements.get("max_peak_memory_mib"), "/validation/requirements/max_peak_memory_mib", findings, 0, exclusive=True)
    critical_components = _require_array(requirements.get("critical_component_ids"), "/validation/requirements/critical_component_ids", findings, 1)
    for index, component_id in enumerate(critical_components):
        if component_id not in component_ids:
            findings.error("reference.component", "/validation/requirements/critical_component_ids/%d" % index, "critical component is not declared")
    critical_masks = {
        item.get("id"): (item.get("component_id"), item.get("feature_id")) for item in masks
        if isinstance(item, Mapping) and item.get("role") == "critical-feature" and item.get("component_id") in critical_components
    }
    global_masks = {
        item.get("id"): item.get("component_id") for item in masks
        if isinstance(item, Mapping) and item.get("role") == "global"
    }
    if not global_masks:
        findings.error("validation.global_mask", "/masks", "contract-component validation requires at least one global acceptance mask")
    missing_mask_components = {
        component_id for component_id in critical_components
        if not any(isinstance(item, Mapping) and item.get("role") == "critical-feature" and item.get("component_id") == component_id for item in masks)
    }
    if missing_mask_components:
        findings.error("validation.critical_mask", "/masks", "critical components need feature-local masks: %s" % ", ".join(sorted(missing_mask_components)))

    measurement = samples.get("measurement") if isinstance(samples.get("measurement"), Mapping) else {}
    measurement_artifact = measurement.get("artifact") if isinstance(measurement.get("artifact"), Mapping) else {}
    measurement_hash = measurement_artifact.get("sha256")
    authority_artifact = authority.get("artifact") if isinstance(authority.get("artifact"), Mapping) else {}
    authority_hash = authority_artifact.get("sha256")
    authority_sample = authority.get("validation_sample") if isinstance(authority.get("validation_sample"), Mapping) else {}
    authority_sample_artifact = authority_sample.get("artifact") if isinstance(authority_sample.get("artifact"), Mapping) else {}
    authority_sample_hash = authority_sample_artifact.get("sha256")
    authority_sample_frame = authority_sample.get("frame")
    required_uncertainty_kinds = {"scanner", "scale", "registration", "sampling", "model"}
    if masks or exclusions:
        required_uncertainty_kinds.add("segmentation")
    missing_uncertainty_kinds = required_uncertainty_kinds - uncertainty_kinds
    component_features: Dict[str, Set[str]] = {}
    component_frames: Dict[str, str] = {}
    for component in components:
        if not isinstance(component, Mapping) or not isinstance(component.get("id"), str):
            continue
        feature_ids = set()
        for feature in component.get("included_features", []):
            if isinstance(feature, str):
                feature_ids.add(feature)
        component_features[component["id"]] = feature_ids
        if isinstance(component.get("frame"), str):
            component_frames[component["id"]] = component["frame"]
    mask_by_id = {item.get("id"): item for item in masks if isinstance(item, Mapping) and isinstance(item.get("id"), str)}
    exclusion_by_id = {
        item.get("id"): item for item in exclusions
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    results = _require_array(validation.get("results"), "/validation/results", findings, 2)
    _check_unique_ids(results, "/validation/results", findings)
    seen_directions: Set[str] = set()
    seen_critical_pairs: Set[Tuple[str, str]] = set()
    seen_global_pairs: Set[Tuple[str, str]] = set()
    evidence_results: List[Mapping[str, Any]] = []
    for index, raw in enumerate(results):
        path = "/validation/results/%d" % index
        allowed = (
            "id", "direction", "metric_kind", "signedness", "signed_bias", "comparison_frame", "transform_ids", "semantic_target",
            "query_artifact_sha256", "target_artifact_sha256", "mask_ids", "exclusion_ids",
            "observed_coverage_percent", "coverage_basis", "completeness", "normal_agreement",
            "section_trim_evidence", "unobserved_face_treatment", "eligible_count", "evaluated_count", "tolerance",
            "within_tolerance_percent", "mean", "rms", "percentiles", "maximum", "realizability_certificate", "backend",
            "batch_size", "peak_memory_mib", "acceptance_criteria", "acceptance_status",
        )
        required = tuple(name for name in allowed if name != "signed_bias")
        item = _require_object(raw, path, findings, required=required, allowed=allowed)
        direction = item.get("direction")
        if direction not in required_directions:
            findings.error("validation.direction", _path(path, "direction"), "unsupported distance direction")
        else:
            seen_directions.add(direction)
        metric_kind = item.get("metric_kind")
        metric_kinds = ("point-to-point", "point-to-surface", "analytic-surface-residual", "section-profile-distance", "trim-boundary-distance")
        if metric_kind not in metric_kinds:
            findings.error("validation.metric_kind", _path(path, "metric_kind"), "unsupported metric kind")
        signedness = item.get("signedness")
        if signedness != "unsigned":
            findings.error("validation.signedness", _path(path, "signedness"), "contract v1 certificates support unsigned nonnegative distance magnitudes only")
        if "signed_bias" in item:
            findings.error("validation.signed_bias", _path(path, "signed_bias"), "contract v1 does not accept uncertified signed-distance bias")
        comparison_frame = _check_id(item.get("comparison_frame"), _path(path, "comparison_frame"), findings)
        if comparison_frame is not None and comparison_frame not in frame_ids:
            findings.error("reference.frame", _path(path, "comparison_frame"), "comparison frame is not declared")
        result_transform_ids = _require_array(item.get("transform_ids"), _path(path, "transform_ids"), findings)
        semantic_target = _require_object(
            item.get("semantic_target"), _path(path, "semantic_target"), findings,
            required=("component_id", "feature_id", "surface_role", "surface_class"),
            allowed=("component_id", "feature_id", "surface_role", "surface_class"),
        )
        target_component = semantic_target.get("component_id")
        target_feature = semantic_target.get("feature_id")
        if target_component not in component_ids:
            findings.error("reference.component", _path(path, "semantic_target/component_id"), "semantic target component is not declared")
        elif target_feature not in component_features.get(target_component, set()):
            findings.error("reference.feature", _path(path, "semantic_target/feature_id"), "semantic target feature is not included by its component")
        surface_role = semantic_target.get("surface_role")
        if surface_role not in ("fit-surface", "datum", "closure", "trim-boundary", "freeform-skin", "section-profile"):
            findings.error("validation.surface_role", _path(path, "semantic_target/surface_role"), "unsupported semantic surface role")
        surface_class = semantic_target.get("surface_class")
        if surface_class not in ("plane", "cylinder", "cone", "sphere", "torus", "spline", "mesh", "mixed"):
            findings.error("validation.surface_class", _path(path, "semantic_target/surface_class"), "unsupported surface class")
        if metric_kind == "analytic-surface-residual" and surface_class not in ("plane", "cylinder", "cone", "sphere", "torus"):
            findings.error("validation.semantic_metric", _path(path, "metric_kind"), "analytic-surface residuals require a declared analytic surface class")
        if metric_kind == "section-profile-distance" and surface_role != "section-profile":
            findings.error("validation.semantic_metric", _path(path, "metric_kind"), "section-profile distance requires a section-profile semantic target")
        if metric_kind == "trim-boundary-distance" and surface_role != "trim-boundary":
            findings.error("validation.semantic_metric", _path(path, "metric_kind"), "trim-boundary distance requires a trim-boundary semantic target")
        if direction == "authority-to-cloud" and metric_kind != "point-to-point":
            findings.error(
                "validation.reverse_metric",
                _path(path, "metric_kind"),
                "authority-to-cloud targets the recorded measurement point artifact and therefore requires point-to-point distance",
            )
        if direction != "authority-to-cloud" and metric_kind == "point-to-point" and surface_class in ("plane", "cylinder", "cone", "sphere", "torus"):
            findings.warning("validation.semantic_metric", _path(path, "metric_kind"), "point-to-point distance does not directly validate the declared analytic surface")
        query_hash = _check_sha(item.get("query_artifact_sha256"), _path(path, "query_artifact_sha256"), findings)
        target_hash = _check_sha(item.get("target_artifact_sha256"), _path(path, "target_artifact_sha256"), findings)
        if direction == "cloud-to-authority" and (query_hash != measurement_hash or target_hash != authority_hash):
            findings.error("lineage.distance_direction", path, "cloud-to-authority must query the measurement artifact against the authority artifact")
        if direction == "authority-to-cloud" and (query_hash != authority_sample_hash or target_hash != measurement_hash):
            findings.error("lineage.distance_direction", path, "authority-to-cloud must query the recorded authority validation sample against the measurement artifact")
        component_frame = component_frames.get(target_component)
        if component_frame is not None and authority_sample_frame is not None and component_frame != authority_sample_frame:
            findings.error("lineage.authority_sample_frame", "/authority/validation_sample/frame", "authority validation sample must use the semantic component frame")
        query_frame = measurement.get("frame") if direction == "cloud-to-authority" else authority_sample_frame
        target_frame = component_frame if direction == "cloud-to-authority" else measurement.get("frame")
        if isinstance(comparison_frame, str) and isinstance(query_frame, str) and isinstance(target_frame, str):
            if query_frame == comparison_frame and target_frame == comparison_frame:
                if result_transform_ids:
                    findings.error("reference.transform_order", _path(path, "transform_ids"), "no transforms are needed when both artifacts already use comparison_frame")
            elif query_frame == comparison_frame:
                _ordered_chain_reaches(target_frame, comparison_frame, result_transform_ids, transform_by_id, _path(path, "transform_ids"), findings)
            elif target_frame == comparison_frame:
                _ordered_chain_reaches(query_frame, comparison_frame, result_transform_ids, transform_by_id, _path(path, "transform_ids"), findings)
            else:
                findings.error("lineage.comparison_frame", _path(path, "comparison_frame"), "one comparison artifact must already use comparison_frame so one ordered chain is unambiguous")
        result_masks = _require_array(item.get("mask_ids"), _path(path, "mask_ids"), findings, 1)
        if len(result_masks) != 1:
            findings.error("validation.result_scope", _path(path, "mask_ids"), "each acceptance result must identify exactly one global or critical-feature mask")
        result_critical_masks: List[str] = []
        result_global_masks: List[str] = []
        for mask_index, mask_id in enumerate(result_masks):
            if mask_id not in mask_ids:
                findings.error("reference.mask", _path(path, "mask_ids/%d" % mask_index), "result mask is not declared")
                continue
            mask = mask_by_id.get(mask_id, {})
            if comparison_frame is not None and mask.get("frame") != comparison_frame:
                findings.error("lineage.mask_frame", _path(path, "mask_ids/%d" % mask_index), "result mask must be defined in comparison_frame")
            if target_component is not None and mask.get("component_id") != target_component:
                findings.error("lineage.mask_component", _path(path, "mask_ids/%d" % mask_index), "result mask must belong to the semantic target component")
            if mask_id in critical_masks and isinstance(direction, str):
                result_critical_masks.append(mask_id)
                if mask.get("feature_id") != target_feature:
                    findings.error("lineage.mask_feature", _path(path, "mask_ids/%d" % mask_index), "critical result mask must identify the semantic target feature")
            elif mask_id in global_masks and isinstance(direction, str):
                result_global_masks.append(mask_id)
            elif mask.get("role") not in ("global", "critical-feature"):
                findings.error("validation.result_scope", _path(path, "mask_ids/%d" % mask_index), "acceptance results require a global or critical-feature mask")
        result_exclusions = _require_array(item.get("exclusion_ids"), _path(path, "exclusion_ids"), findings)
        for exclusion_index, exclusion_id in enumerate(result_exclusions):
            if exclusion_id not in exclusion_ids:
                findings.error("reference.exclusion", _path(path, "exclusion_ids/%d" % exclusion_index), "result exclusion is not declared and approved")
                continue
            exclusion = exclusion_by_id.get(exclusion_id, {})
            exclusion_mask = mask_by_id.get(exclusion.get("mask_id"), {})
            if exclusion.get("mask_id") in result_masks:
                findings.error("validation.exclusion_overlap", _path(path, "exclusion_ids/%d" % exclusion_index), "a result cannot exclude a mask that it claims as evaluated evidence")
            excluded_definition = exclusion_mask.get("definition")
            if isinstance(excluded_definition, Mapping) and any(
                _json_semantic_equal(mask_by_id.get(mask_id, {}).get("definition"), excluded_definition)
                for mask_id in result_masks
            ):
                findings.error("validation.exclusion_overlap", _path(path, "exclusion_ids/%d" % exclusion_index), "a result cannot exclude geometry identical to a claimed evidence mask")
            if comparison_frame is not None and exclusion_mask.get("frame") != comparison_frame:
                findings.error("lineage.exclusion_frame", _path(path, "exclusion_ids/%d" % exclusion_index), "result exclusion mask must be defined in comparison_frame")
            if target_component is not None and exclusion_mask.get("component_id") != target_component:
                findings.error("lineage.exclusion_component", _path(path, "exclusion_ids/%d" % exclusion_index), "result exclusion mask must belong to the semantic target component")
        if not result_exclusions and isinstance(direction, str):
            for critical_mask_id in result_critical_masks:
                seen_critical_pairs.add((critical_mask_id, direction))
            for global_mask_id in result_global_masks:
                seen_global_pairs.add((global_mask_id, direction))
        coverage = _check_number(item.get("observed_coverage_percent"), _path(path, "observed_coverage_percent"), findings, 0)
        if coverage is not None and coverage > 100:
            findings.error("validation.coverage", _path(path, "observed_coverage_percent"), "observed coverage cannot exceed 100 percent")
        coverage_basis = item.get("coverage_basis")
        if coverage_basis not in ("query-points", "surface-area", "trim-length"):
            findings.error("validation.coverage_basis", _path(path, "coverage_basis"), "unsupported coverage basis")
        if metric_kind == "point-to-point" and coverage_basis != "query-points":
            findings.error(
                "validation.metric_coverage",
                _path(path, "coverage_basis"),
                "point-to-point distance coverage must be reported over query points",
            )
        if coverage_basis == "surface-area":
            findings.error(
                "validation.metric_coverage",
                _path(path, "coverage_basis"),
                "feature-contract v1 has no area-weighting derivation record and cannot substantiate surface-area coverage",
            )
        if coverage_basis == "trim-length" and not (
            metric_kind == "trim-boundary-distance" and surface_role == "trim-boundary"
        ):
            findings.error(
                "validation.metric_coverage",
                _path(path, "coverage_basis"),
                "trim-length coverage requires a trim-boundary distance metric and trim-boundary semantic target",
            )
        if direction == "authority-to-cloud" and coverage_basis != "query-points":
            findings.error(
                "validation.reverse_coverage",
                _path(path, "coverage_basis"),
                "authority-to-cloud coverage is measured over the recorded authority query points",
            )
        completeness = item.get("completeness")
        if completeness not in ("complete-observed", "partial-observed", "unobserved-closure"):
            findings.error("validation.completeness", _path(path, "completeness"), "unsupported completeness class")
        elif coverage is not None:
            if completeness == "complete-observed" and not math.isclose(coverage, 100.0, abs_tol=1e-9):
                findings.error("validation.completeness", _path(path, "observed_coverage_percent"), "complete-observed evidence must report 100 percent coverage")
            if completeness == "partial-observed" and not (0 < coverage < 100):
                findings.error("validation.completeness", _path(path, "observed_coverage_percent"), "partial-observed evidence requires coverage strictly between 0 and 100")
            if completeness == "unobserved-closure" and coverage != 0:
                findings.error("validation.completeness", _path(path, "observed_coverage_percent"), "unobserved closure evidence must report zero observed coverage")
        if completeness == "unobserved-closure" and surface_role != "closure":
            findings.error("validation.unobserved_surface", _path(path, "semantic_target/surface_role"), "unobserved-closure completeness is only valid for a closure surface")
        treatment = item.get("unobserved_face_treatment")
        treatments = ("none-unobserved", "excluded-with-approved-mask", "separately-reported", "closure-only-not-fit-evidence")
        if treatment not in treatments:
            findings.error("validation.unobserved_treatment", _path(path, "unobserved_face_treatment"), "unsupported unobserved-face treatment")
        if completeness == "complete-observed" and treatment != "none-unobserved":
            findings.error("validation.unobserved_treatment", _path(path, "unobserved_face_treatment"), "complete observed targets must use none-unobserved")
        if completeness in ("partial-observed", "unobserved-closure") and treatment == "none-unobserved":
            findings.error("validation.unobserved_treatment", _path(path, "unobserved_face_treatment"), "partial or unobserved targets require explicit unobserved-face treatment")
        if treatment == "excluded-with-approved-mask" and not result_exclusions:
            findings.error("validation.unobserved_exclusion", _path(path, "exclusion_ids"), "excluded unobserved faces require an approved exclusion")

        eligible_count = _check_integer(item.get("eligible_count"), _path(path, "eligible_count"), findings, 1)
        evaluated_count = _check_integer(item.get("evaluated_count"), _path(path, "evaluated_count"), findings, 1)
        query_point_count = _as_integer(measurement.get("point_count") if direction == "cloud-to-authority" else authority_sample.get("point_count"))
        if eligible_count is not None and query_point_count is not None and eligible_count > query_point_count:
            findings.error("validation.eligible_count", _path(path, "eligible_count"), "eligible count cannot exceed the direction's recorded query artifact point count")
        if eligible_count is not None and evaluated_count is not None and evaluated_count != eligible_count:
            findings.error("validation.evaluation_selection", _path(path, "evaluated_count"), "every eligible point must be evaluated; subsampling requires a separately identified sample artifact")
        if result_global_masks and not result_exclusions and eligible_count is not None and query_point_count is not None and eligible_count != query_point_count:
            findings.error("validation.global_count", _path(path, "eligible_count"), "an exclusion-free contract-component global result must cover the complete direction query artifact")
        if (
            evaluated_count is not None
            and query_point_count is not None
            and evaluated_count > query_point_count
        ):
            findings.error("validation.evaluated_count", _path(path, "evaluated_count"), "evaluated count cannot exceed the direction's recorded query artifact point count")

        normal = _require_object(
            item.get("normal_agreement"), _path(path, "normal_agreement"), findings,
            required=("applicability", "source_normal_quality", "quality_evidence", "evaluated_count"),
            allowed=(
                "applicability", "source_normal_quality", "quality_evidence", "evaluated_count",
                "mean_angle_deg", "p95_angle_deg", "maximum_angle_deg", "angle_threshold_deg",
                "exceeding_count", "realizability_certificate", "reason",
            ),
        )
        normal_applicability = normal.get("applicability")
        normal_quality = normal.get("source_normal_quality")
        if normal_applicability not in ("required", "informational", "not-applicable"):
            findings.error("validation.normal_applicability", _path(path, "normal_agreement/applicability"), "unsupported normal-check applicability")
        if normal_quality not in ("verified", "estimated", "unreliable", "absent"):
            findings.error("validation.normal_quality", _path(path, "normal_agreement/source_normal_quality"), "unsupported normal quality")
        normal_count = _check_integer(normal.get("evaluated_count"), _path(path, "normal_agreement/evaluated_count"), findings, 0)
        if normal_count is not None and evaluated_count is not None and normal_count > evaluated_count:
            findings.error("validation.normal_count", _path(path, "normal_agreement/evaluated_count"), "normal evaluated count cannot exceed the distance evaluated count")
        if normal_applicability == "required" and normal_count is not None and evaluated_count is not None and normal_count != evaluated_count:
            findings.error("validation.normal_count", _path(path, "normal_agreement/evaluated_count"), "required normal evidence must cover every distance-evaluated query point")
        angle_values = []
        for field in ("mean_angle_deg", "p95_angle_deg", "maximum_angle_deg"):
            if field in normal:
                angle = _check_number(normal.get(field), _path(path, "normal_agreement/" + field), findings, 0)
                if angle is not None and angle > 180:
                    findings.error("validation.normal_angle", _path(path, "normal_agreement/" + field), "normal angle cannot exceed 180 degrees")
                angle_values.append(angle)
            else:
                angle_values.append(None)
        if normal_applicability in ("required", "informational"):
            if normal_count in (None, 0) or any(angle is None for angle in angle_values):
                findings.error("validation.normal_metrics", _path(path, "normal_agreement"), "applicable normal checks require count, mean, P95, and maximum")
            if normal_applicability == "required" and normal_quality in ("unreliable", "absent"):
                findings.error("validation.normal_quality", _path(path, "normal_agreement/source_normal_quality"), "required normal agreement needs verified or estimated source normals")
            if source.get("point_record") not in ("xyz-normals", "xyz-normals-rgb"):
                findings.error("validation.normal_source", _path(path, "normal_agreement"), "normal agreement requires a source record with normal columns")
            mean_angle, p95_angle, max_angle = angle_values
            if mean_angle is not None and max_angle is not None and _strictly_greater(mean_angle, max_angle):
                findings.error("validation.normal_order", _path(path, "normal_agreement"), "normal mean cannot exceed the maximum angle")
            if p95_angle is not None and max_angle is not None and _strictly_greater(p95_angle, max_angle):
                findings.error("validation.normal_order", _path(path, "normal_agreement"), "normal P95 cannot exceed the maximum angle")
        elif normal_applicability == "not-applicable":
            if normal_count not in (None, 0) or any(angle is not None for angle in angle_values):
                findings.error("validation.normal_not_applicable", _path(path, "normal_agreement"), "not-applicable normal checks must have zero count and no angle statistics")
            if any(name in normal for name in ("angle_threshold_deg", "exceeding_count", "realizability_certificate")):
                findings.error("validation.normal_not_applicable", _path(path, "normal_agreement"), "not-applicable normal checks must not carry an angle realizability certificate")
            if not isinstance(normal.get("reason"), str) or not normal.get("reason", "").strip():
                findings.error("validation.normal_reason", _path(path, "normal_agreement/reason"), "not-applicable normal checks require a reason")
        section_trim = _require_object(
            item.get("section_trim_evidence"), _path(path, "section_trim_evidence"), findings,
            required=("defining_section_ids", "trim_boundary_ids", "passed"),
            allowed=("defining_section_ids", "trim_boundary_ids", "evidence_sha256", "passed", "not_applicable_reason"),
        )
        section_ids = _require_array(section_trim.get("defining_section_ids"), _path(path, "section_trim_evidence/defining_section_ids"), findings)
        trim_ids = _require_array(section_trim.get("trim_boundary_ids"), _path(path, "section_trim_evidence/trim_boundary_ids"), findings)
        for collection_name, identifiers in (("defining_section_ids", section_ids), ("trim_boundary_ids", trim_ids)):
            seen_identifiers: Set[str] = set()
            for identifier_index, identifier in enumerate(identifiers):
                checked = _check_id(identifier, _path(path, "section_trim_evidence/%s/%d" % (collection_name, identifier_index)), findings)
                if checked is not None and checked in seen_identifiers:
                    findings.error("reference.duplicate_id", _path(path, "section_trim_evidence/%s/%d" % (collection_name, identifier_index)), "evidence identifier is duplicated")
                if checked is not None:
                    seen_identifiers.add(checked)
        if metric_kind == "section-profile-distance" and not section_ids:
            findings.error("validation.semantic_metric", _path(path, "section_trim_evidence/defining_section_ids"), "section-profile metrics require defining-section evidence")
        if metric_kind == "trim-boundary-distance" and not trim_ids:
            findings.error("validation.semantic_metric", _path(path, "section_trim_evidence/trim_boundary_ids"), "trim-boundary metrics require trim-boundary evidence")
        if coverage_basis == "trim-length" and not trim_ids:
            findings.error(
                "validation.metric_coverage",
                _path(path, "section_trim_evidence/trim_boundary_ids"),
                "trim-length coverage requires recorded trim-boundary evidence",
            )
        if section_ids or trim_ids:
            _check_sha(section_trim.get("evidence_sha256"), _path(path, "section_trim_evidence/evidence_sha256"), findings)
            if section_trim.get("passed") is not True:
                findings.error("validation.section_trim_gate", _path(path, "section_trim_evidence/passed"), "declared section/trim evidence must pass")
        elif not isinstance(section_trim.get("not_applicable_reason"), str) or not section_trim.get("not_applicable_reason", "").strip():
            findings.error("validation.section_trim_reason", _path(path, "section_trim_evidence/not_applicable_reason"), "empty section/trim evidence requires a reason")
        section_trim_inconclusive = not (section_ids or trim_ids)
        tolerance = _check_number(item.get("tolerance"), _path(path, "tolerance"), findings, 0, exclusive=True)
        within = _check_number(item.get("within_tolerance_percent"), _path(path, "within_tolerance_percent"), findings, 0)
        if within is not None and within > 100:
            findings.error("validation.percentage", _path(path, "within_tolerance_percent"), "percentage cannot exceed 100")
        mean = _check_number(item.get("mean"), _path(path, "mean"), findings, 0)
        rms = _check_number(item.get("rms"), _path(path, "rms"), findings, 0)
        if mean is not None and rms is not None and _strictly_less(rms, mean):
            findings.error("validation.rms", _path(path, "rms"), "RMS distance cannot be below mean distance")
        signed_bias = item.get("signed_bias") if signedness == "signed" else None
        if _is_number(signed_bias) and mean is not None and _strictly_greater(abs(float(signed_bias)), mean):
            findings.error("validation.signed_bias", _path(path, "signed_bias"), "absolute signed bias cannot exceed the mean distance magnitude")
        maximum = _check_number(item.get("maximum"), _path(path, "maximum"), findings, 0)
        percentile_results = _require_array(item.get("percentiles"), _path(path, "percentiles"), findings, 1)
        actual_percentiles: Set[float] = set()
        percentile_constraints: List[Tuple[int, int, float, float, str]] = []
        certificate_percentiles: List[Tuple[float, float, str]] = []
        previous_percentile = -math.inf
        previous_distance = -math.inf
        for percentile_index, raw_percentile in enumerate(percentile_results):
            percentile_path = _path(_path(path, "percentiles"), percentile_index)
            percentile_item = _require_object(raw_percentile, percentile_path, findings, required=("percentile", "distance"), allowed=("percentile", "distance"))
            percentile = _check_number(percentile_item.get("percentile"), _path(percentile_path, "percentile"), findings, 0, exclusive=True)
            distance = _check_number(percentile_item.get("distance"), _path(percentile_path, "distance"), findings, 0)
            if percentile is not None:
                if percentile > 100:
                    findings.error("validation.percentile", _path(percentile_path, "percentile"), "percentile cannot exceed 100")
                if percentile in actual_percentiles:
                    findings.error("validation.percentile_duplicate", _path(percentile_path, "percentile"), "percentile result is duplicated")
                if percentile < previous_percentile:
                    findings.error("validation.percentile_order", _path(percentile_path, "percentile"), "percentiles must be sorted ascending")
                actual_percentiles.add(percentile)
                previous_percentile = percentile
            if distance is not None:
                if _strictly_less(distance, previous_distance):
                    findings.error("validation.distance_order", _path(percentile_path, "distance"), "distance percentiles must be nondecreasing")
                if maximum is not None and _strictly_greater(distance, maximum):
                    findings.error("validation.maximum", _path(percentile_path, "distance"), "percentile distance cannot exceed maximum")
                if percentile is not None and math.isclose(percentile, 100.0, abs_tol=1e-12) and maximum is not None and not math.isclose(distance, maximum, rel_tol=1e-9, abs_tol=0.0):
                    findings.error("validation.maximum", _path(percentile_path, "distance"), "the 100th-percentile distance must equal maximum")
                if percentile in invariant_percentiles and evaluated_count is not None and distance is not None:
                    lower_index, upper_index, fraction = _fixed_percentile_position(evaluated_count, percentile)
                    if 0 <= lower_index <= upper_index <= evaluated_count - 1:
                        percentile_constraints.append((lower_index, upper_index, fraction, distance, percentile_path))
                        certificate_percentiles.append((percentile, distance, percentile_path))
                        tail_count = evaluated_count - upper_index
                        tail_fraction = tail_count / evaluated_count
                        mean_floor = distance * tail_fraction
                        rms_floor = distance * math.sqrt(tail_fraction)
                        if mean is not None and _strictly_less(mean, mean_floor):
                            findings.error(
                                "validation.percentile_mean_bound",
                                percentile_path,
                                "mean is below the necessary lower bound implied by this percentile and evaluated count",
                            )
                        if rms is not None and _strictly_less(rms, rms_floor):
                            findings.error(
                                "validation.percentile_rms_bound",
                                percentile_path,
                                "RMS is below the necessary lower bound implied by this percentile and evaluated count",
                            )
                        lower_fraction = (lower_index + 1) / evaluated_count
                        remaining_fraction = (evaluated_count - lower_index - 1) / evaluated_count
                        percentile_mean_ceiling = math.fsum(
                            (lower_fraction * distance, remaining_fraction * maximum)
                        ) if maximum is not None else None
                        percentile_rms_ceiling = math.hypot(
                            math.sqrt(lower_fraction) * distance,
                            math.sqrt(remaining_fraction) * maximum,
                        ) if maximum is not None else None
                        if mean is not None and percentile_mean_ceiling is not None and _strictly_greater(mean, percentile_mean_ceiling):
                            findings.error(
                                "validation.percentile_mean_ceiling",
                                percentile_path,
                                "mean exceeds the necessary upper bound implied by this percentile, evaluated count, and maximum",
                            )
                        if rms is not None and percentile_rms_ceiling is not None and _strictly_greater(rms, percentile_rms_ceiling):
                            findings.error(
                                "validation.percentile_rms_ceiling",
                                percentile_path,
                                "RMS exceeds the necessary upper bound implied by this percentile, evaluated count, and maximum",
                            )
                previous_distance = distance
        if evaluated_count is not None and evaluated_count > 0 and maximum is not None:
            known_order_statistics: Dict[int, Tuple[float, str]] = {}

            def endpoints_close(left: float, right: float) -> bool:
                scale = max(abs(left), abs(right))
                return math.isclose(left, right, rel_tol=1e-9, abs_tol=scale * 1e-12)

            def assign_endpoint(index: int, value: float, endpoint_path: str) -> bool:
                scale = max(abs(value), abs(maximum))
                slack = scale * 1e-10
                if not math.isfinite(value) or value < -slack or value > maximum + slack:
                    findings.error(
                        "validation.percentile_interpolation",
                        endpoint_path,
                        "percentile constraints infer an order statistic outside the finite nonnegative distance range",
                    )
                    return False
                normalized = min(max(value, 0.0), maximum)
                existing = known_order_statistics.get(index)
                if existing is not None:
                    if not endpoints_close(existing[0], normalized):
                        findings.error(
                            "validation.percentile_interpolation",
                            endpoint_path,
                            "percentile constraints assign inconsistent values to one shared order statistic",
                        )
                    return False
                known_order_statistics[index] = (normalized, endpoint_path)
                return True

            assign_endpoint(evaluated_count - 1, maximum, _path(path, "maximum"))
            fractional_by_bin: Dict[Tuple[int, int], List[Tuple[float, float, str]]] = {}
            for lower_index, upper_index, fraction, distance, constraint_path in percentile_constraints:
                if lower_index == upper_index:
                    assign_endpoint(lower_index, distance, constraint_path)
                else:
                    fractional_by_bin.setdefault((lower_index, upper_index), []).append(
                        (fraction, distance, constraint_path)
                    )

            for (lower_index, upper_index), observations in fractional_by_bin.items():
                distinct_observations = sorted(observations)
                first_fraction, first_distance, first_path = distinct_observations[0]
                last_fraction, last_distance, _ = distinct_observations[-1]
                fraction_span = last_fraction - first_fraction
                if len(distinct_observations) >= 2 and fraction_span > 0:
                    slope = (last_distance - first_distance) / fraction_span
                    assign_endpoint(lower_index, first_distance - first_fraction * slope, first_path)
                    assign_endpoint(upper_index, first_distance + (1.0 - first_fraction) * slope, first_path)

            constraint_adjacency: Dict[int, List[int]] = {}
            for constraint_index, (lower_index, upper_index, _, _, _) in enumerate(percentile_constraints):
                if lower_index == upper_index:
                    continue
                constraint_adjacency.setdefault(lower_index, []).append(constraint_index)
                constraint_adjacency.setdefault(upper_index, []).append(constraint_index)
            pending_endpoints = deque(known_order_statistics)
            propagated_endpoints: Set[int] = set()
            while pending_endpoints:
                endpoint_index = pending_endpoints.popleft()
                if endpoint_index in propagated_endpoints:
                    continue
                propagated_endpoints.add(endpoint_index)
                for constraint_index in constraint_adjacency.get(endpoint_index, ()):
                    lower_index, upper_index, fraction, distance, constraint_path = percentile_constraints[constraint_index]
                    lower_known = known_order_statistics.get(lower_index)
                    upper_known = known_order_statistics.get(upper_index)
                    if lower_known is not None and upper_known is None:
                        inferred_upper = (distance - (1.0 - fraction) * lower_known[0]) / fraction
                        if assign_endpoint(upper_index, inferred_upper, constraint_path):
                            pending_endpoints.append(upper_index)
                    elif upper_known is not None and lower_known is None:
                        inferred_lower = (distance - fraction * upper_known[0]) / (1.0 - fraction)
                        if assign_endpoint(lower_index, inferred_lower, constraint_path):
                            pending_endpoints.append(lower_index)

            for lower_index, upper_index, fraction, distance, constraint_path in percentile_constraints:
                lower_known = known_order_statistics.get(lower_index)
                upper_known = known_order_statistics.get(upper_index)
                if lower_known is None or upper_known is None:
                    continue
                expected_distance = lower_known[0] if lower_index == upper_index else (
                    (1.0 - fraction) * lower_known[0] + fraction * upper_known[0]
                )
                if not endpoints_close(distance, expected_distance):
                    findings.error(
                        "validation.percentile_interpolation",
                        constraint_path,
                        "percentile distance is inconsistent with the shared linear-interpolation order statistics",
                    )

            ordered_known = sorted(known_order_statistics.items())
            for (_, (left_value, _)), (_, (right_value, right_path)) in zip(ordered_known, ordered_known[1:]):
                if _strictly_greater(left_value, right_value):
                    findings.error(
                        "validation.percentile_interpolation",
                        right_path,
                        "inferred order statistics must be nondecreasing",
                    )

        missing_percentiles = required_percentiles - actual_percentiles
        if missing_percentiles:
            findings.error("validation.required_percentile", _path(path, "percentiles"), "missing required percentile(s): %s" % ", ".join("%g" % value for value in sorted(missing_percentiles)))
        if tuple(percentile for percentile, _, _ in certificate_percentiles) != REQUIRED_PERCENTILE_PROFILE:
            findings.error(
                "validation.percentile_profile",
                _path(path, "percentiles"),
                "contract v1 results require exactly P50, P95, P98, and P99 in ascending order",
            )
        certified_within_count = _check_realizability_certificate(
            item.get("realizability_certificate"),
            _path(path, "realizability_certificate"),
            evaluated_count,
            maximum,
            tolerance,
            None,
            within,
            certificate_percentiles,
            mean,
            rms,
            findings,
        )
        certified_within_percent = (
            None
            if certified_within_count is None or evaluated_count is None
            else 100.0 * certified_within_count / evaluated_count
        )
        if mean is not None and maximum is not None and _strictly_greater(mean, maximum):
            findings.error("validation.maximum", _path(path, "mean"), "mean distance cannot exceed maximum")
        if rms is not None and maximum is not None and _strictly_greater(rms, maximum):
            findings.error("validation.maximum", _path(path, "rms"), "RMS distance cannot exceed maximum")
        if mean is not None and rms is not None and maximum is not None:
            moment_bound = math.sqrt(mean) * math.sqrt(maximum)
            if not math.isfinite(moment_bound) or _strictly_greater(rms, moment_bound):
                findings.error("validation.moment_consistency", _path(path, "rms"), "RMS squared cannot exceed mean times maximum for nonnegative bounded distances")
        if evaluated_count is not None and maximum is not None:
            if mean is not None and _strictly_less(mean, maximum / evaluated_count):
                findings.error("validation.maximum_mean_bound", _path(path, "mean"), "mean is below maximum divided by evaluated count")
            if rms is not None and _strictly_less(rms, maximum / math.sqrt(evaluated_count)):
                findings.error("validation.maximum_rms_bound", _path(path, "rms"), "RMS is below maximum divided by the square root of evaluated count")
            if evaluated_count > 1 and mean is not None and rms is not None and maximum > 0:
                mean_ratio = mean / maximum
                remaining_sum_ratio = evaluated_count * mean_ratio - 1.0
                finite_count_rms_floor = maximum * (
                    math.hypot(1.0, remaining_sum_ratio / math.sqrt(evaluated_count - 1))
                    / math.sqrt(evaluated_count)
                )
                if _strictly_less(rms, finite_count_rms_floor):
                    findings.error(
                        "validation.finite_count_rms_bound",
                        _path(path, "rms"),
                        "RMS is below the finite-count lower bound implied by mean and the recorded maximum",
                    )
        backend = item.get("backend")
        if backend not in ("stdlib-bounded", "scipy-ckdtree", "open3d-kdtree", "cad-kernel"):
            findings.error("validation.backend", _path(path, "backend"), "unsupported distance backend")
        elif direction == "authority-to-cloud" and backend not in ("stdlib-bounded", "scipy-ckdtree", "open3d-kdtree"):
            findings.error(
                "validation.reverse_backend",
                _path(path, "backend"),
                "authority-to-cloud point evidence requires a point-sample or KD-tree backend",
            )
        elif backend in ("stdlib-bounded", "scipy-ckdtree", "open3d-kdtree") and metric_kind != "point-to-point":
            findings.error("validation.backend_metric", _path(path, "backend"), "point-sample and KD-tree backends only establish point-to-point distance")
        elif metric_kind in ("point-to-surface", "analytic-surface-residual", "section-profile-distance", "trim-boundary-distance") and backend != "cad-kernel":
            findings.error("validation.backend_metric", _path(path, "backend"), "surface, section, and trim metrics require the CAD-kernel backend")
        _check_integer(item.get("batch_size"), _path(path, "batch_size"), findings, 1)
        peak_memory = _check_number(item.get("peak_memory_mib"), _path(path, "peak_memory_mib"), findings, 0)
        if peak_memory is not None and memory_budget is not None and peak_memory > memory_budget:
            findings.error("validation.memory_budget", _path(path, "peak_memory_mib"), "result exceeded declared peak-memory budget")
        criteria = _require_object(
            item.get("acceptance_criteria"), _path(path, "acceptance_criteria"), findings,
            required=("minimum_within_tolerance_percent", "minimum_observed_coverage_percent", "maximum_distance", "percentile_gates"),
            allowed=(
                "minimum_within_tolerance_percent", "minimum_observed_coverage_percent", "maximum_distance",
                "maximum_normal_mean_angle_deg", "maximum_normal_p95_angle_deg", "maximum_normal_angle_deg",
                "percentile_gates",
            ),
        )
        minimum_within = _check_number(criteria.get("minimum_within_tolerance_percent"), _path(path, "acceptance_criteria/minimum_within_tolerance_percent"), findings, 0, exclusive=True)
        minimum_coverage = _check_number(criteria.get("minimum_observed_coverage_percent"), _path(path, "acceptance_criteria/minimum_observed_coverage_percent"), findings, 0)
        maximum_gate = _check_number(criteria.get("maximum_distance"), _path(path, "acceptance_criteria/maximum_distance"), findings, 0)
        gate_items = _require_array(criteria.get("percentile_gates"), _path(path, "acceptance_criteria/percentile_gates"), findings, 1)
        percentile_map: Dict[float, float] = {}
        for raw_percentile in percentile_results:
            if isinstance(raw_percentile, Mapping) and _is_number(raw_percentile.get("percentile")) and _is_number(raw_percentile.get("distance")):
                percentile_map[float(raw_percentile["percentile"])] = float(raw_percentile["distance"])
        physical_failures: List[str] = []
        dimensionless_failures: List[str] = []
        inconclusive_reasons: List[str] = []
        if minimum_within is not None and certified_within_percent is not None and certified_within_percent < minimum_within:
            physical_failures.append("within-tolerance percentage below minimum")
        if minimum_coverage is not None and coverage is not None and coverage < minimum_coverage:
            dimensionless_failures.append("observed coverage percentage below minimum")
        if maximum_gate is not None and maximum is not None and maximum > maximum_gate:
            physical_failures.append("maximum distance above gate")
        gate_percentiles: Set[float] = set()
        for gate_index, raw_gate in enumerate(gate_items):
            gate_path = _path(path, "acceptance_criteria/percentile_gates/%d" % gate_index)
            gate = _require_object(raw_gate, gate_path, findings, required=("percentile", "maximum_distance"), allowed=("percentile", "maximum_distance"))
            gate_percentile = _check_number(gate.get("percentile"), _path(gate_path, "percentile"), findings, 0, exclusive=True)
            gate_distance = _check_number(gate.get("maximum_distance"), _path(gate_path, "maximum_distance"), findings, 0)
            if gate_percentile is not None:
                if gate_percentile in gate_percentiles:
                    findings.error("validation.percentile_duplicate", _path(gate_path, "percentile"), "acceptance percentile gate is duplicated")
                gate_percentiles.add(gate_percentile)
                if gate_percentile not in percentile_map:
                    findings.error("validation.acceptance_percentile", _path(gate_path, "percentile"), "acceptance gate has no matching measured percentile")
                elif gate_distance is not None and percentile_map[gate_percentile] > gate_distance:
                    physical_failures.append("P%g distance above gate" % gate_percentile)
        if not required_percentiles.issubset(gate_percentiles):
            findings.error("validation.acceptance_percentile", _path(path, "acceptance_criteria/percentile_gates"), "acceptance criteria must gate every required percentile")
        if tuple(
            float(raw_gate.get("percentile"))
            for raw_gate in gate_items
            if isinstance(raw_gate, Mapping) and _is_number(raw_gate.get("percentile"))
        ) != REQUIRED_PERCENTILE_PROFILE:
            findings.error(
                "validation.acceptance_percentile_profile",
                _path(path, "acceptance_criteria/percentile_gates"),
                "contract v1 acceptance gates require exactly P50, P95, P98, and P99 in ascending order",
            )

        normal_gate_names = (
            ("maximum_normal_mean_angle_deg", angle_values[0], "normal mean angle above gate"),
            ("maximum_normal_p95_angle_deg", angle_values[1], "normal P95 angle above gate"),
            ("maximum_normal_angle_deg", angle_values[2], "normal maximum angle above gate"),
        )
        normal_gates: List[Optional[float]] = []
        for gate_name, observed_angle, failure_reason in normal_gate_names:
            if gate_name in criteria or normal_applicability == "required":
                gate_value = _check_number(criteria.get(gate_name), _path(path, "acceptance_criteria/" + gate_name), findings, 0)
                if gate_value is not None and gate_value >= 90:
                    findings.error("validation.normal_gate", _path(path, "acceptance_criteria/" + gate_name), "normal acceptance gates must be below 90 degrees")
                if gate_value is not None and observed_angle is not None and observed_angle > gate_value:
                    dimensionless_failures.append(failure_reason)
                normal_gates.append(gate_value)
            else:
                normal_gates.append(None)
        if all(gate is not None for gate in normal_gates) and not (normal_gates[0] <= normal_gates[1] <= normal_gates[2]):
            findings.error("validation.normal_gate_order", _path(path, "acceptance_criteria"), "normal mean, P95, and maximum gates must be nondecreasing")
        if normal_applicability != "required" and any(name in criteria for name, _, _ in normal_gate_names):
            findings.error("validation.normal_gate_applicability", _path(path, "acceptance_criteria"), "normal acceptance gates are only valid when normal agreement is required")
        if normal_applicability in ("required", "informational"):
            angle_threshold = _check_number(
                normal.get("angle_threshold_deg"),
                _path(path, "normal_agreement/angle_threshold_deg"),
                findings,
                0,
            )
            exceeding_count = _check_integer(
                normal.get("exceeding_count"),
                _path(path, "normal_agreement/exceeding_count"),
                findings,
                0,
            )
            if exceeding_count is not None and normal_count is not None and exceeding_count > normal_count:
                findings.error("validation.normal_threshold_count", _path(path, "normal_agreement/exceeding_count"), "normal exceeding count cannot exceed evaluated count")
            if normal_applicability == "required" and angle_threshold is not None and normal_gates[2] is not None and not _numbers_close(angle_threshold, normal_gates[2]):
                findings.error("validation.normal_threshold", _path(path, "normal_agreement/angle_threshold_deg"), "normal certificate threshold must equal the maximum-angle acceptance gate")
            normal_within_count = None if normal_count is None or exceeding_count is None else normal_count - exceeding_count
            certificate_threshold = normal_gates[2] if normal_applicability == "required" else angle_threshold
            normal_percentiles = [] if angle_values[1] is None else [
                (95.0, angle_values[1], _path(path, "normal_agreement/p95_angle_deg"))
            ]
            _check_realizability_certificate(
                normal.get("realizability_certificate"),
                _path(path, "normal_agreement/realizability_certificate"),
                normal_count,
                angle_values[2],
                certificate_threshold,
                normal_within_count,
                None,
                normal_percentiles,
                angle_values[0],
                None,
                findings,
                _path(path, "normal_agreement/mean_angle_deg"),
                None,
            )

        if completeness != "complete-observed":
            inconclusive_reasons.append("semantic target is not completely observed")
        if direction != "authority-to-cloud" and metric_kind == "point-to-point" and surface_class in ("plane", "cylinder", "cone", "sphere", "torus"):
            inconclusive_reasons.append("point-to-point evidence does not validate the declared analytic surface")
        if section_trim_inconclusive:
            inconclusive_reasons.append("defining section and trim-boundary validation was not performed")

        if dimensionless_failures:
            derived_status = "fail"
            reasons = dimensionless_failures + physical_failures
        elif source.get("units_status") in ("provisional", "unknown"):
            derived_status = "inconclusive"
            reasons = ["source units are not verified; physical tolerance verdicts cannot be derived"]
            reasons.extend(inconclusive_reasons)
        elif uncertainty_model == "reported-only":
            derived_status = "inconclusive"
            reasons = ["reported-only uncertainty lacks independently validated combination evidence"]
            reasons.extend(inconclusive_reasons)
        elif missing_uncertainty_kinds:
            derived_status = "inconclusive"
            reasons = ["uncertainty budget omits required terms: %s" % ", ".join(sorted(missing_uncertainty_kinds))]
            reasons.extend(inconclusive_reasons)
        elif physical_failures:
            derived_status = "fail"
            reasons = physical_failures
        elif tolerance is not None and expanded_uncertainty is not None and tolerance <= expanded_uncertainty:
            derived_status = "inconclusive"
            reasons = ["tolerance is not above expanded uncertainty"]
            reasons.extend(inconclusive_reasons)
        elif inconclusive_reasons:
            derived_status = "inconclusive"
            reasons = inconclusive_reasons
        else:
            derived_status = "pass"
            reasons = []
        claimed_status = item.get("acceptance_status")
        if claimed_status not in ("pass", "fail", "inconclusive"):
            findings.error("validation.acceptance_status", _path(path, "acceptance_status"), "unknown claimed acceptance status")
        elif claimed_status != derived_status:
            findings.error("validation.acceptance_claim", _path(path, "acceptance_status"), "claimed status %s differs from derived status %s" % (claimed_status, derived_status))
        evidence_results.append(
            {
                "id": item.get("id"),
                "claimed_status": claimed_status,
                "derived_status": derived_status,
                "reasons": _bounded_unique_reasons(reasons),
            }
        )
    if seen_directions != required_directions:
        findings.error("validation.result_directions", "/validation/results", "results must include both distance directions")
    required_critical_pairs = {(mask_id, direction) for mask_id in critical_masks for direction in required_directions}
    missing_critical_pairs = required_critical_pairs - seen_critical_pairs
    if missing_critical_pairs:
        findings.error(
            "validation.local_results", "/validation/results",
            "critical masks require their own component result in both directions: %s"
            % ", ".join("%s/%s" % pair for pair in sorted(missing_critical_pairs)),
        )
    required_global_pairs = {(mask_id, direction) for mask_id in global_masks for direction in required_directions}
    missing_global_pairs = required_global_pairs - seen_global_pairs
    if missing_global_pairs:
        findings.error(
            "validation.global_results", "/validation/results",
            "global masks require their own exclusion-free result in both directions: %s"
            % ", ".join("%s/%s" % pair for pair in sorted(missing_global_pairs)),
        )
    derived = [result["derived_status"] for result in evidence_results]
    aggregate = "fail" if "fail" in derived else "inconclusive" if "inconclusive" in derived else "pass" if derived else "not-evaluated"
    return aggregate, evidence_results


def _validate_contract_impl(contract: Any, schema: Any = None) -> Dict[str, Any]:
    """Validate one decoded contract and return a stable JSON-serializable report."""

    findings = Findings()
    if schema is None:
        try:
            schema = load_json_strict(DEFAULT_SCHEMA_PATH)
        except (OSError, ValueError, json.JSONDecodeError):
            findings.error("schema.load", "/", "cannot load bundled structural authority")
            return findings.report(contract)
    supported_issues = check_supported_schema(schema)
    for issue in supported_issues:
        findings.error(issue.code, issue.path, issue.message)
    if supported_issues:
        return findings.report(contract)
    structural_issues = validate_instance(contract, schema)
    for issue in structural_issues:
        findings.error(issue.code, issue.path, issue.message)
    if structural_issues:
        return findings.report(contract)
    required_top = (
        "schema_version", "contract_id", "units", "frames", "transforms", "source", "samples",
        "authority", "components", "parameters", "masks", "exclusions", "uncertainty", "validation",
    )
    root = _require_object(contract, "", findings, required=required_top, allowed=required_top)
    if root.get("schema_version") != SCHEMA_VERSION:
        findings.error("schema.version", "/schema_version", "expected schema version %s" % SCHEMA_VERSION)
    _check_id(root.get("contract_id"), "/contract_id", findings)
    _walk_private_values(root, "", findings)

    units = _require_object(root.get("units"), "/units", findings, required=("linear", "angular"), allowed=("linear", "angular"))
    linear_unit = units.get("linear")
    angular_unit = units.get("angular")
    if linear_unit not in ("mm", "cm", "m", "in"):
        findings.error("units.linear", "/units/linear", "expected mm, cm, m, or in")
    if angular_unit not in ("deg", "rad"):
        findings.error("units.angular", "/units/angular", "expected deg or rad")

    frames = _require_array(root.get("frames"), "/frames", findings, 2)
    frame_ids = _check_unique_ids(frames, "/frames", findings)
    frame_handedness: Dict[str, str] = {}
    for index, raw in enumerate(frames):
        path = "/frames/%d" % index
        item = _require_object(raw, path, findings, required=("id", "handedness", "x_axis", "y_axis", "z_axis"), allowed=("id", "handedness", "x_axis", "y_axis", "z_axis", "origin"))
        frame_id = item.get("id")
        handedness = item.get("handedness")
        if handedness not in ("right", "left"):
            findings.error("frame.handedness", _path(path, "handedness"), "expected right or left")
        if isinstance(frame_id, str) and handedness in ("right", "left"):
            frame_handedness[frame_id] = handedness
        for key in ("x_axis", "y_axis", "z_axis"):
            if not isinstance(item.get(key), str) or not item.get(key, "").strip():
                findings.error("frame.axis", _path(path, key), "axis meaning must be nonempty text")

    source = _check_source(root.get("source"), frame_ids, findings)
    transforms = _require_array(root.get("transforms"), "/transforms", findings, 1)
    transform_edges, transform_by_id = _check_transforms(transforms, frame_ids, frame_handedness, source, findings)
    authority = _check_authority(root.get("authority"), frame_ids, findings)
    source_frame = source.get("frame") if isinstance(source.get("frame"), str) else None
    components, component_ids = _check_components(root.get("components"), authority, frame_ids, source_frame, transform_edges, findings)
    masks, mask_ids = _check_masks(root.get("masks"), frame_ids, components, component_ids, findings)
    samples = _check_samples(root.get("samples"), source, frame_ids, transform_edges, findings)
    _check_parameters(root.get("parameters"), component_ids, masks, mask_ids, linear_unit, angular_unit, findings)
    exclusions, exclusion_ids = _check_exclusions(root.get("exclusions"), mask_ids, findings)
    expanded_uncertainty, uncertainty_kinds = _check_uncertainty(root.get("uncertainty"), linear_unit, findings)
    uncertainty_model = root.get("uncertainty", {}).get("model") if isinstance(root.get("uncertainty"), Mapping) else None
    evidence_status, evidence_results = _check_validation(
        root.get("validation"), source, samples, authority, components, component_ids, masks, mask_ids,
        exclusions, exclusion_ids, expanded_uncertainty, uncertainty_model, uncertainty_kinds, frame_ids, transform_by_id, findings,
    )
    return findings.report(contract, evidence_status, evidence_results)


def validate_contract(contract: Any, schema: Any = None) -> Dict[str, Any]:
    """Validate decoded input and fail closed on unexpected malformed semantic leaves."""

    try:
        return _validate_contract_impl(contract, schema)
    except (ArithmeticError, TypeError, ValueError, LookupError):
        findings = Findings()
        findings.error(
            "validation.malformed_semantics",
            "/",
            "decoded contract contains malformed values that cannot be evaluated safely",
        )
        return findings.report(contract)
