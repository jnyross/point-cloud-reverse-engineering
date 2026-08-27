"""Deterministic, dependency-light point-cloud evidence helpers.

The stdlib distance backend is an exact point-to-point canary over explicitly
bounded samples.  It is not a substitute for point-to-B-rep surface distance.
An explicit SciPy backend is available when scipy is already installed.
"""

from __future__ import annotations

import hashlib
import heapq
import itertools
import math
import os
import re
import secrets
import stat
from bisect import bisect_right
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from .contract import canonical_json_sha256, load_json_strict


Point = Tuple[float, float, float]
ALGORITHM_VERSION = "pcre-tools-1.0"
STDLIB_MAX_PAIR_EVALUATIONS = 10_000_000
MAX_SAMPLE_POINTS = 100_000
MAX_PLY_VERTEX_COUNT = 2**53 - 1
MAX_MASK_DEFINITIONS = 1024
MAX_SEED = 2**32 - 1
MAX_CLOUD_LINE_CHARS = 1024 * 1024
MAX_PLY_HEADER_LINES = 10_000
MAX_PLY_HEADER_CHARS = 8 * 1024 * 1024
MAX_PLY_VERTEX_PROPERTIES = 1024
MAX_PLY_HEADER_TOKEN_CHARS = 256
MAX_PLY_ELEMENTS = 1024
REALIZABILITY_PERCENTILES = (50.0, 95.0, 98.0, 99.0)
FRAME_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
ASCII_INTEGER_RE = re.compile(r"^[+-]?[0-9]+$")
ASCII_DECIMAL_RE = re.compile(r"^[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?)|(?:\.[0-9]+))(?:[eE][+-]?[0-9]+)?$")

PLY_INTEGER_RANGES = {
    "char": (-2**7, 2**7 - 1),
    "int8": (-2**7, 2**7 - 1),
    "uchar": (0, 2**8 - 1),
    "uint8": (0, 2**8 - 1),
    "short": (-2**15, 2**15 - 1),
    "int16": (-2**15, 2**15 - 1),
    "ushort": (0, 2**16 - 1),
    "uint16": (0, 2**16 - 1),
    "int": (-2**31, 2**31 - 1),
    "int32": (-2**31, 2**31 - 1),
    "uint": (0, 2**32 - 1),
    "uint32": (0, 2**32 - 1),
}
PLY_FLOAT_TYPES = {"float", "double", "float32", "float64"}
PLY_SCALAR_TYPES = set(PLY_INTEGER_RANGES) | PLY_FLOAT_TYPES


class CloudFormatError(ValueError):
    """Raised when point input cannot be parsed without guessing."""


SourceStamp = Tuple[int, int, int, int]


def _stamp_from_status(status: os.stat_result) -> SourceStamp:
    return (status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns)


def _open_regular_source(path: Path) -> Tuple[int, SourceStamp]:
    """Open and pin a regular source without ever blocking on a FIFO/device."""

    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            raise CloudFormatError("point-cloud source must be a regular file")
        return descriptor, _stamp_from_status(status)
    except Exception:
        os.close(descriptor)
        raise


def _identity_from_fd(descriptor: int) -> Dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return {"sha256": digest.hexdigest(), "byte_count": size}


def _path_stamp(path: Path) -> SourceStamp:
    status = path.stat()
    if not stat.S_ISREG(status.st_mode):
        raise CloudFormatError("source content changed while evidence was being collected")
    return _stamp_from_status(status)


def _verify_pinned_source(
    path: Path,
    descriptor: int,
    expected_identity: Mapping[str, Any],
    expected_stamp: SourceStamp,
) -> None:
    try:
        descriptor_stamp = _stamp_from_status(os.fstat(descriptor))
        actual_identity = _identity_from_fd(descriptor)
        current_path_stamp = _path_stamp(path)
    except OSError as error:
        raise CloudFormatError("source content changed while evidence was being collected") from error
    if descriptor_stamp != expected_stamp or current_path_stamp != expected_stamp or actual_identity != expected_identity:
        raise CloudFormatError("source content changed while evidence was being collected")


def file_identity(path: Path) -> Dict[str, Any]:
    descriptor, source_stamp = _open_regular_source(path)
    try:
        identity = _identity_from_fd(descriptor)
        _verify_pinned_source(path, descriptor, identity, source_stamp)
        return identity
    finally:
        os.close(descriptor)


def _coordinate_text(value: float) -> str:
    if value == 0:
        return "0"
    return format(value, ".17g")


def canonical_point_bytes(point: Point) -> bytes:
    return (" ".join(_coordinate_text(value) for value in point) + "\n").encode("ascii")


def _finite_point(values: Sequence[str], context: str) -> Point:
    if len(values) < 3:
        raise CloudFormatError("%s: expected at least X Y Z" % context)
    decoded: List[float] = []
    for token in values[:3]:
        if not ASCII_DECIMAL_RE.fullmatch(token):
            raise CloudFormatError("%s: nonnumeric X Y Z" % context)
        try:
            parsed = float(token)
            exact = Decimal(token)
        except (ValueError, InvalidOperation) as error:
            raise CloudFormatError("%s: nonnumeric X Y Z" % context) from error
        if parsed == 0 and not exact.is_zero():
            raise CloudFormatError("%s: coordinate underflows the supported IEEE-754 range" % context)
        decoded.append(parsed)
    point = (decoded[0], decoded[1], decoded[2])
    if not all(math.isfinite(value) for value in point):
        raise CloudFormatError("%s: NaN or infinity is not valid point evidence" % context)
    return point


def _bounded_readline(handle: Any, context: str) -> str:
    line = handle.readline(MAX_CLOUD_LINE_CHARS + 1)
    if len(line) > MAX_CLOUD_LINE_CHARS:
        raise CloudFormatError("%s exceeds the hard per-line input cap" % context)
    return line


def _parse_ply_scalar(token: str, scalar_type: str, context: str) -> float | int:
    if len(token) > MAX_PLY_HEADER_TOKEN_CHARS:
        raise CloudFormatError("%s contains an overlong scalar token" % context)
    if scalar_type in PLY_INTEGER_RANGES:
        if not ASCII_INTEGER_RE.fullmatch(token):
            raise CloudFormatError("%s contains a malformed integer property" % context)
        try:
            value = int(token, 10)
        except ValueError as error:
            raise CloudFormatError("%s contains a malformed integer property" % context) from error
        lower, upper = PLY_INTEGER_RANGES[scalar_type]
        if value < lower or value > upper:
            raise CloudFormatError("%s contains an out-of-range integer property" % context)
        return value
    if scalar_type in PLY_FLOAT_TYPES:
        if not ASCII_DECIMAL_RE.fullmatch(token):
            raise CloudFormatError("%s contains a malformed floating-point property" % context)
        try:
            value = float(token)
            exact = Decimal(token)
        except (ValueError, InvalidOperation) as error:
            raise CloudFormatError("%s contains a malformed floating-point property" % context) from error
        if not math.isfinite(value):
            raise CloudFormatError("%s contains a non-finite floating-point property" % context)
        if value == 0 and not exact.is_zero():
            raise CloudFormatError("%s contains a property below the supported IEEE-754 range" % context)
        return value
    raise CloudFormatError("PLY declares an unsupported scalar property type")


def _validate_ply_record(
    fields: Sequence[str],
    properties: Sequence[Tuple[str, str, Optional[str], str]],
    context: str,
) -> None:
    cursor = 0
    for kind, first_type, second_type, _ in properties:
        if cursor >= len(fields):
            raise CloudFormatError("%s token count does not match declared properties" % context)
        if kind == "scalar":
            _parse_ply_scalar(fields[cursor], first_type, context)
            cursor += 1
            continue
        list_count = _parse_ply_scalar(fields[cursor], first_type, context)
        cursor += 1
        if not isinstance(list_count, int) or list_count < 0:
            raise CloudFormatError("%s contains an invalid list-property count" % context)
        if list_count > len(fields) - cursor:
            raise CloudFormatError("%s token count does not match the declared list property" % context)
        if second_type is None:
            raise CloudFormatError("PLY list property has no declared value type")
        for item_index in range(list_count):
            _parse_ply_scalar(fields[cursor + item_index], second_type, context)
        cursor += list_count
    if cursor != len(fields):
        raise CloudFormatError("%s contains undeclared trailing property tokens" % context)


def _detect_format_fd(path: Path, requested: str, descriptor: int) -> str:
    if requested != "auto":
        return requested
    suffix = path.suffix.lower()
    if suffix == ".ply":
        return "ply"
    if suffix in (".asc", ".xyz", ".txt", ".pts", ".csv"):
        return "xyz"
    os.lseek(descriptor, 0, os.SEEK_SET)
    first = os.read(descriptor, 64).splitlines()[0].strip() if os.fstat(descriptor).st_size else b""
    os.lseek(descriptor, 0, os.SEEK_SET)
    if first == b"ply":
        return "ply"
    return "xyz"


def _iter_points_fd(descriptor: int, fmt: str, skip_lines: int = 0) -> Iterator[Point]:
    if isinstance(skip_lines, bool) or not isinstance(skip_lines, int) or skip_lines < 0:
        raise ValueError("skip-lines must be a nonnegative integer")
    os.lseek(descriptor, 0, os.SEEK_SET)
    if fmt == "xyz":
        with os.fdopen(os.dup(descriptor), "r", encoding="utf-8-sig", errors="strict") as handle:
            line_number = 0
            while True:
                line = _bounded_readline(handle, "point-cloud line")
                if not line:
                    break
                line_number += 1
                if line_number <= skip_lines:
                    continue
                stripped = line.strip()
                if not stripped or stripped.startswith(("#", "//", ";")):
                    continue
                if "," in stripped:
                    fields = [field.strip() for field in stripped.split(",")]
                    if len(fields) < 3 or any(not field for field in fields[:3]):
                        raise CloudFormatError("line %d: CSV X Y Z fields must be present" % line_number)
                else:
                    fields = stripped.split()
                yield _finite_point(fields, "line %d" % line_number)
        return
    if fmt != "ply":
        raise CloudFormatError("unsupported input format %r; use auto, xyz, or ply" % fmt)
    if skip_lines:
        raise ValueError("skip-lines is only defined for headerless XYZ-style input")
    with os.fdopen(os.dup(descriptor), "r", encoding="ascii", errors="strict") as handle:
        if _bounded_readline(handle, "PLY line").strip() != "ply":
            raise CloudFormatError("PLY input does not start with 'ply'")
        line_number = 1
        header_chars = 4
        format_seen = False
        vertex_element_seen = False
        element_names: set[str] = set()
        elements: List[Dict[str, Any]] = []
        current_element: Optional[Dict[str, Any]] = None
        while True:
            if line_number >= MAX_PLY_HEADER_LINES:
                raise CloudFormatError("PLY header exceeds the hard line-count cap")
            line = _bounded_readline(handle, "PLY header line")
            line_number += 1
            if not line:
                raise CloudFormatError("PLY header ended before end_header")
            header_chars += len(line)
            if header_chars > MAX_PLY_HEADER_CHARS:
                raise CloudFormatError("PLY header exceeds the hard total-size cap")
            fields = line.strip().split()
            if not fields:
                continue
            if any(len(field) > MAX_PLY_HEADER_TOKEN_CHARS for field in fields):
                raise CloudFormatError("PLY header token exceeds the hard length cap")
            if fields[0] in ("comment", "obj_info"):
                continue
            if fields[0] == "format":
                if fields != ["format", "ascii", "1.0"] or format_seen:
                    raise CloudFormatError("PLY must contain exactly one 'format ascii 1.0' declaration")
                format_seen = True
            elif fields[0] == "element":
                if not format_seen:
                    raise CloudFormatError("PLY format declaration must precede data elements")
                if len(fields) != 3:
                    raise CloudFormatError("PLY element declaration needs exactly three tokens")
                element_name = fields[1]
                if element_name in element_names:
                    raise CloudFormatError("PLY element names must be unique")
                if not ASCII_INTEGER_RE.fullmatch(fields[2]):
                    raise CloudFormatError("PLY element count must be an integer")
                try:
                    element_count = int(fields[2])
                except ValueError as error:
                    raise CloudFormatError("PLY element count must be an integer") from error
                if element_count < 0 or element_count > MAX_PLY_VERTEX_COUNT:
                    raise CloudFormatError("PLY element count is outside the supported signed 64-bit range")
                if element_name == "vertex":
                    if vertex_element_seen:
                        raise CloudFormatError("PLY must declare exactly one vertex element")
                    if elements:
                        raise CloudFormatError("PLY vertex element must be the first data element")
                    vertex_element_seen = True
                current_element = {"name": element_name, "count": element_count, "properties": []}
                elements.append(current_element)
                element_names.add(element_name)
                if len(elements) > MAX_PLY_ELEMENTS:
                    raise CloudFormatError("PLY element count exceeds the hard declaration cap")
            elif fields[0] == "property":
                if current_element is None:
                    raise CloudFormatError("PLY property appears before any element declaration")
                scalar_ok = len(fields) == 3 and fields[1] in PLY_SCALAR_TYPES
                list_ok = (
                    len(fields) == 5
                    and fields[1] == "list"
                    and fields[2] in PLY_INTEGER_RANGES
                    and fields[3] in PLY_SCALAR_TYPES
                )
                if not (scalar_ok or list_ok):
                    raise CloudFormatError("malformed PLY property declaration")
                if current_element["name"] == "vertex" and list_ok:
                    raise CloudFormatError("list-valued vertex properties are unsupported")
                property_name = fields[2] if scalar_ok else fields[4]
                if any(existing[3] == property_name for existing in current_element["properties"]):
                    raise CloudFormatError("PLY property names must be unique within an element")
                if scalar_ok:
                    current_element["properties"].append(("scalar", fields[1], None, property_name))
                else:
                    current_element["properties"].append(("list", fields[2], fields[3], property_name))
                if len(current_element["properties"]) > MAX_PLY_VERTEX_PROPERTIES:
                    raise CloudFormatError("PLY element property count exceeds the hard cap")
            elif fields[0] == "end_header":
                if len(fields) != 1:
                    raise CloudFormatError("end_header must be the only token on its line")
                break
            else:
                raise CloudFormatError("unsupported PLY header directive")
        if not format_seen or not vertex_element_seen:
            raise CloudFormatError("PLY must declare ASCII format and vertex count")
        vertex_properties = elements[0]["properties"]
        vertex_property_names = [property_record[3] for property_record in vertex_properties]
        try:
            indices = [vertex_property_names.index(axis) for axis in ("x", "y", "z")]
        except ValueError as error:
            raise CloudFormatError("PLY vertex element must declare x, y, and z properties") from error
        for element_index, element in enumerate(elements):
            properties = element["properties"]
            for record_index in range(element["count"]):
                line = _bounded_readline(handle, "PLY body line")
                line_number += 1
                if not line:
                    raise CloudFormatError("PLY ended before every declared element record was present")
                fields = line.split()
                context = "line %d PLY element record" % line_number
                _validate_ply_record(fields, properties, context)
                if element_index == 0:
                    yield _finite_point([fields[index] for index in indices], "line %d" % line_number)
        while True:
            line = _bounded_readline(handle, "PLY trailing line")
            if not line:
                break
            line_number += 1
            if line.strip():
                raise CloudFormatError("PLY contains undeclared trailing body data")


def iter_points(path: Path, input_format: str = "auto", skip_lines: int = 0) -> Iterator[Point]:
    """Yield points from one pinned regular-file descriptor without guessing units."""

    descriptor, source_stamp = _open_regular_source(path)
    try:
        identity = _identity_from_fd(descriptor)
        detected_format = _detect_format_fd(path, input_format, descriptor)
        yield from _iter_points_fd(descriptor, detected_format, skip_lines)
        _verify_pinned_source(path, descriptor, identity, source_stamp)
    finally:
        os.close(descriptor)


class CloudAccumulator:
    def __init__(self) -> None:
        self.count = 0
        self.minimum = [math.inf, math.inf, math.inf]
        self.maximum = [-math.inf, -math.inf, -math.inf]
        self.digest = hashlib.sha256()

    def add(self, point: Point) -> None:
        self.count += 1
        self.digest.update(canonical_point_bytes(point))
        for axis, value in enumerate(point):
            self.minimum[axis] = min(self.minimum[axis], value)
            self.maximum[axis] = max(self.maximum[axis], value)

    def report(self) -> Dict[str, Any]:
        if not self.count:
            raise CloudFormatError("point cloud contains no valid points")
        return {
            "point_count": self.count,
            "canonical_points_sha256": self.digest.hexdigest(),
            "bounds": {"min": self.minimum, "max": self.maximum},
        }


class RankedSampler:
    """Keep the k lowest role-separated SHA-256 ranks in O(k) memory."""

    def __init__(self, count: int, seed: int, role: str) -> None:
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("sample count must be a positive integer")
        if count > MAX_SAMPLE_POINTS:
            raise ValueError("sample count exceeds the hard %d-point memory cap" % MAX_SAMPLE_POINTS)
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= MAX_SEED:
            raise ValueError("sampling seed must be an integer in [0, %d]" % MAX_SEED)
        if role not in ("measurement", "display", "distance-a", "distance-b"):
            raise ValueError("unknown sampling role %r" % role)
        self.count = count
        self.seed = seed
        self.role = role
        self._heap: List[Tuple[int, int, Point]] = []

    def add(self, point: Point, index: int) -> None:
        digest = hashlib.sha256()
        digest.update(ALGORITHM_VERSION.encode("ascii"))
        digest.update(b"\0")
        digest.update(self.role.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(self.seed).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(index).encode("ascii"))
        digest.update(b"\0")
        digest.update(canonical_point_bytes(point))
        rank = int.from_bytes(digest.digest(), "big")
        candidate = (-rank, -index, point)
        if len(self._heap) < self.count:
            heapq.heappush(self._heap, candidate)
        elif candidate > self._heap[0]:
            heapq.heapreplace(self._heap, candidate)

    def points(self, source_order: bool = False) -> List[Point]:
        key = (lambda item: item[1]) if source_order else (lambda item: (item[0], item[1]))
        ordered = sorted(((-rank, -index, point) for rank, index, point in self._heap), key=key)
        return [point for _, _, point in ordered]


def analyze_cloud(path: Path, input_format: str = "auto", skip_lines: int = 0) -> Dict[str, Any]:
    descriptor, source_stamp = _open_regular_source(path)
    try:
        identity = _identity_from_fd(descriptor)
        detected_format = _detect_format_fd(path, input_format, descriptor)
        accumulator = CloudAccumulator()
        for point in _iter_points_fd(descriptor, detected_format, skip_lines):
            accumulator.add(point)
        _verify_pinned_source(path, descriptor, identity, source_stamp)
        return {
            "artifact": identity,
            **accumulator.report(),
            "parser": {"format": detected_format, "skip_lines": skip_lines},
        }
    finally:
        os.close(descriptor)


def _mask_number(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError("%s must be a finite number, not a boolean" % context)
    return float(value)


@dataclass(frozen=True)
class CompiledMaskDefinition:
    kind: str
    values: Tuple[float, ...]


@dataclass(frozen=True)
class CompiledMask:
    frame: str
    include: Tuple[CompiledMaskDefinition, ...]
    exclude: Tuple[CompiledMaskDefinition, ...]
    sha256: str


def _compile_definition(definition: Mapping[str, Any]) -> CompiledMaskDefinition:
    kind = definition.get("type")
    if kind == "aabb":
        if set(definition) != {"type", "min", "max"}:
            raise ValueError("mask definition contains unsupported or missing properties")
        lower = definition.get("min")
        upper = definition.get("max")
        if not isinstance(lower, list) or not isinstance(upper, list) or len(lower) != 3 or len(upper) != 3:
            raise ValueError("AABB mask requires three-value min and max")
        minimum = [_mask_number(value, "AABB minimum") for value in lower]
        maximum = [_mask_number(value, "AABB maximum") for value in upper]
        if any(left > right for left, right in zip(minimum, maximum)):
            raise ValueError("AABB mask minimum must not exceed maximum")
        return CompiledMaskDefinition("aabb", tuple(minimum + maximum))
    if kind == "sphere":
        if set(definition) != {"type", "center", "radius"}:
            raise ValueError("mask definition contains unsupported or missing properties")
        center = definition.get("center")
        radius = definition.get("radius")
        if not isinstance(center, list) or len(center) != 3:
            raise ValueError("sphere mask requires center and positive radius")
        center_values = [_mask_number(value, "sphere center") for value in center]
        radius_value = _mask_number(radius, "sphere radius")
        if radius_value <= 0:
            raise ValueError("sphere mask radius must be positive")
        return CompiledMaskDefinition("sphere", tuple(center_values + [radius_value]))
    raise ValueError("mask definition must be aabb or sphere")


def _compiled_contains(definition: CompiledMaskDefinition, point: Point) -> bool:
    if definition.kind == "aabb":
        return all(definition.values[axis] <= point[axis] <= definition.values[axis + 3] for axis in range(3))
    center = definition.values[:3]
    radius = definition.values[3]
    distance = math.dist(point, center)
    if not math.isfinite(distance):
        raise OverflowError("sphere mask distance produced a non-finite value")
    return distance <= radius


def compile_mask(mask: Mapping[str, Any]) -> CompiledMask:
    allowed = {"frame", "include", "exclude"}
    unknown = set(mask) - allowed
    if unknown:
        raise ValueError("mask contains unsupported properties")
    frame = mask.get("frame")
    if not isinstance(frame, str) or not FRAME_ID_RE.fullmatch(frame):
        raise ValueError("mask frame must be an explicit portable identifier")
    raw_collections = {name: mask.get(name, []) for name in ("include", "exclude")}
    if any(not isinstance(definitions, list) for definitions in raw_collections.values()):
        raise ValueError("mask include and exclude must be arrays")
    definition_count = sum(len(definitions) for definitions in raw_collections.values())
    if definition_count > MAX_MASK_DEFINITIONS:
        raise ValueError("mask exceeds the hard %d-definition cap" % MAX_MASK_DEFINITIONS)
    compiled: Dict[str, Tuple[CompiledMaskDefinition, ...]] = {}
    for collection in ("include", "exclude"):
        definitions = raw_collections[collection]
        compiled_items: List[CompiledMaskDefinition] = []
        for definition in definitions:
            if not isinstance(definition, Mapping):
                raise ValueError("mask definitions must be objects")
            compiled_items.append(_compile_definition(definition))
        compiled[collection] = tuple(compiled_items)
    return CompiledMask(frame, compiled["include"], compiled["exclude"], canonical_json_sha256(mask))


def load_mask(path: Optional[Path]) -> Tuple[Optional[CompiledMask], Optional[str]]:
    if path is None:
        return None, None
    mask = load_json_strict(path)
    if not isinstance(mask, Mapping):
        raise ValueError("mask root must be an object")
    compiled = compile_mask(mask)
    return compiled, compiled.sha256


def mask_accepts(mask: Optional[CompiledMask], point: Point) -> bool:
    if mask is None:
        return True
    included = not mask.include or any(_compiled_contains(definition, point) for definition in mask.include)
    excluded = any(_compiled_contains(definition, point) for definition in mask.exclude)
    return included and not excluded


def scan_and_sample(
    path: Path,
    count: int,
    seed: int,
    role: str,
    input_format: str = "auto",
    skip_lines: int = 0,
    mask: Optional[Any] = None,
    frame: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[Point]]:
    if frame is not None and (not isinstance(frame, str) or not FRAME_ID_RE.fullmatch(frame)):
        raise ValueError("comparison frame must be a portable kebab-case identifier")
    compiled_mask = compile_mask(mask) if isinstance(mask, Mapping) else mask
    if compiled_mask is not None and not isinstance(compiled_mask, CompiledMask):
        raise ValueError("mask must be a compiled mask or mask object")
    if compiled_mask is not None:
        if frame is None:
            raise ValueError("masked sampling requires an explicit comparison frame")
        if compiled_mask.frame != frame:
            raise ValueError("mask frame does not match the explicit comparison frame")
    descriptor, source_stamp = _open_regular_source(path)
    try:
        identity = _identity_from_fd(descriptor)
        detected_format = _detect_format_fd(path, input_format, descriptor)
        all_points = CloudAccumulator()
        eligible = CloudAccumulator()
        sampler = RankedSampler(count, seed, role)
        for index, point in enumerate(_iter_points_fd(descriptor, detected_format, skip_lines)):
            all_points.add(point)
            if mask_accepts(compiled_mask, point):
                eligible.add(point)
                sampler.add(point, index)
        _verify_pinned_source(path, descriptor, identity, source_stamp)
    finally:
        os.close(descriptor)
    source_report = all_points.report()
    if not eligible.count:
        raise CloudFormatError("mask leaves zero eligible points")
    retains_every_eligible_point = eligible.count <= count
    points = sampler.points(source_order=retains_every_eligible_point)
    sample_accumulator = CloudAccumulator()
    for point in points:
        sample_accumulator.add(point)
    sample_report = sample_accumulator.report()
    masked = compiled_mask is not None
    method = "masked-hash-rank" if masked else "full" if retains_every_eligible_point else "hash-rank"
    parameters: Dict[str, Any] = {}
    if method in ("hash-rank", "masked-hash-rank"):
        parameters["target_count"] = count
    if masked:
        parameters.update({"eligible_count": eligible.count, "mask_sha256": compiled_mask.sha256})
    sample_details = {
        **sample_report,
        "role": role,
        "source_sha256": identity["sha256"],
        "source_point_count": source_report["point_count"],
        "method": method,
        "algorithm_version": ALGORITHM_VERSION,
        "seed": seed,
        "parameters": parameters,
    }
    source_details = {"artifact": identity, **source_report}
    if frame is not None:
        sample_details["frame"] = frame
        sample_details["bounds"] = {"frame": frame, **sample_report["bounds"]}
        source_details["frame"] = frame
        source_details["bounds"] = {"frame": frame, **source_report["bounds"]}
    report = {
        "source": source_details,
        "eligible_point_count": eligible.count,
        "observed_coverage_percent": 100.0 * eligible.count / source_report["point_count"],
        "sample": sample_details,
    }
    return report, points


def assert_distinct_files(source: Path, destination: Path) -> None:
    source_resolved = source.resolve(strict=True)
    destination_resolved = destination.resolve(strict=False)
    if source_resolved == destination_resolved:
        raise ValueError("sample destination resolves to the immutable source")
    if destination.exists() and os.path.samefile(source, destination):
        raise ValueError("sample destination is the source or a hardlink to it")


def _same_inode_at(directory_descriptor: int, name: str, device: int, inode: int) -> bool:
    try:
        status = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return status.st_dev == device and status.st_ino == inode


def _open_output_directory(path: Path) -> Tuple[int, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    if not getattr(os, "O_DIRECTORY", 0) or not getattr(os, "O_NOFOLLOW", 0):
        raise OSError("safe descriptor-relative output publication is unsupported on this platform")
    descriptor = os.open(path, flags)
    status = os.fstat(descriptor)
    if not stat.S_ISDIR(status.st_mode):
        os.close(descriptor)
        raise OSError("sample output parent must be a real directory")
    return descriptor, status


def _public_directory_matches(path: Path, expected: os.stat_result) -> bool:
    try:
        descriptor, actual = _open_output_directory(path)
    except OSError:
        return False
    try:
        return actual.st_dev == expected.st_dev and actual.st_ino == expected.st_ino
    finally:
        os.close(descriptor)


def _create_output_temporary(directory_descriptor: int) -> Tuple[int, str]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    for _ in range(128):
        name = ".pcre-sample-%s.tmp" % secrets.token_hex(16)
        try:
            return os.open(name, flags, 0o600, dir_fd=directory_descriptor), name
        except FileExistsError:
            continue
    raise FileExistsError("could not allocate an exclusive sample temporary")


def _fsync_output_directory(directory_descriptor: int) -> None:
    try:
        os.fsync(directory_descriptor)
    except OSError as error:
        if error.errno not in (getattr(os, "EINVAL", 22), getattr(os, "ENOTSUP", 95), getattr(os, "EBADF", 9)):
            raise


def write_xyz(
    path: Path,
    points: Sequence[Point],
    overwrite: bool = False,
    source_path: Optional[Path] = None,
) -> Dict[str, Any]:
    if source_path is not None:
        assert_distinct_files(source_path, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.name or path.name in (".", ".."):
        raise ValueError("sample destination must name a file")
    directory_descriptor, directory_status = _open_output_directory(path.parent)
    source_descriptor: Optional[int] = None
    source_stamp: Optional[SourceStamp] = None
    descriptor: Optional[int] = None
    temporary_name: Optional[str] = None
    published = False
    success = False
    owned_device: Optional[int] = None
    owned_inode: Optional[int] = None
    try:
        if source_path is not None:
            source_descriptor, source_stamp = _open_regular_source(source_path)
        try:
            destination_status = os.stat(path.name, dir_fd=directory_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            destination_status = None
        if destination_status is not None and not overwrite:
            raise FileExistsError("sample destination already exists; pass --overwrite to replace it")
        if source_descriptor is not None and destination_status is not None:
            source_status = os.fstat(source_descriptor)
            if destination_status.st_dev == source_status.st_dev and destination_status.st_ino == source_status.st_ino:
                raise ValueError("sample destination is the source or a hardlink to it")
            try:
                followed_destination = os.stat(path.name, dir_fd=directory_descriptor, follow_symlinks=True)
            except (FileNotFoundError, OSError):
                followed_destination = None
            if (
                followed_destination is not None
                and followed_destination.st_dev == source_status.st_dev
                and followed_destination.st_ino == source_status.st_ino
            ):
                raise ValueError("sample destination resolves to the immutable source")
        descriptor, temporary_name = _create_output_temporary(directory_descriptor)
        status = os.fstat(descriptor)
        owned_device, owned_inode = status.st_dev, status.st_ino
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            for point in points:
                if len(point) != 3 or any(
                    isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value))
                    for value in point
                ):
                    raise ValueError("sample output points must be finite numeric XYZ triples")
                handle.write(canonical_point_bytes(point))
            handle.flush()
            os.fsync(handle.fileno())
        if not _same_inode_at(directory_descriptor, temporary_name, owned_device, owned_inode):
            raise RuntimeError("exclusive sample temporary was replaced before publication")
        if not _public_directory_matches(path.parent, directory_status):
            raise RuntimeError("sample output parent changed before publication")
        if source_descriptor is not None and source_path is not None and source_stamp is not None:
            if _stamp_from_status(os.fstat(source_descriptor)) != source_stamp or _path_stamp(source_path) != source_stamp:
                raise RuntimeError("immutable source changed before sample publication")
        if overwrite:
            os.replace(
                temporary_name,
                path.name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
            )
        else:
            os.link(
                temporary_name,
                path.name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            os.unlink(temporary_name, dir_fd=directory_descriptor)
        published = True
        _fsync_output_directory(directory_descriptor)
        if not _public_directory_matches(path.parent, directory_status):
            raise RuntimeError("sample output parent changed during publication")
        if not _same_inode_at(directory_descriptor, path.name, owned_device, owned_inode):
            raise RuntimeError("published sample entry was replaced before verification")
        published_descriptor = os.open(
            path.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory_descriptor,
        )
        try:
            published_status = os.fstat(published_descriptor)
            if published_status.st_dev != owned_device or published_status.st_ino != owned_inode:
                raise RuntimeError("published sample identity differs from the owned temporary")
            identity = _identity_from_fd(published_descriptor)
        finally:
            os.close(published_descriptor)
        if source_descriptor is not None and source_path is not None and source_stamp is not None:
            if _stamp_from_status(os.fstat(source_descriptor)) != source_stamp or _path_stamp(source_path) != source_stamp:
                raise RuntimeError("immutable source changed during sample publication")
        success = True
        return identity
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_name is not None and owned_device is not None and owned_inode is not None:
            if _same_inode_at(directory_descriptor, temporary_name, owned_device, owned_inode):
                os.unlink(temporary_name, dir_fd=directory_descriptor)
        if published and not success and owned_device is not None and owned_inode is not None:
            if _same_inode_at(directory_descriptor, path.name, owned_device, owned_inode):
                os.unlink(path.name, dir_fd=directory_descriptor)
                _fsync_output_directory(directory_descriptor)
        if source_descriptor is not None:
            os.close(source_descriptor)
        os.close(directory_descriptor)


def determinant3(matrix: Sequence[float]) -> float:
    if len(matrix) != 16:
        raise ValueError("transform matrix needs 16 row-major values")
    a, b, c = matrix[0], matrix[1], matrix[2]
    d, e, f = matrix[4], matrix[5], matrix[6]
    g, h, i = matrix[8], matrix[9], matrix[10]
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def transform_point(matrix: Sequence[float], point: Point) -> Point:
    if len(matrix) != 16 or not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in matrix):
        raise ValueError("transform matrix needs 16 finite row-major values")
    if not all(math.isfinite(float(value)) for value in point):
        raise ValueError("transform point must be finite")
    x, y, z = point
    output = []
    for row in range(3):
        offset = row * 4
        value = matrix[offset] * x + matrix[offset + 1] * y + matrix[offset + 2] * z + matrix[offset + 3]
        if not math.isfinite(value):
            raise OverflowError("transform produced a non-finite coordinate")
        output.append(value)
    w = matrix[12] * x + matrix[13] * y + matrix[14] * z + matrix[15]
    if not math.isfinite(w):
        raise OverflowError("transform produced a non-finite homogeneous coordinate")
    if abs(w) < 1e-15:
        raise ValueError("transform maps a canary corner to homogeneous w=0")
    if not math.isclose(w, 1.0, abs_tol=1e-12):
        output = [value / w for value in output]
    if not all(math.isfinite(value) for value in output):
        raise OverflowError("transform normalization produced a non-finite coordinate")
    return (output[0], output[1], output[2])


def _matrix_product(left: Sequence[float], right: Sequence[float]) -> List[float]:
    output = []
    for row in range(4):
        for column in range(4):
            value = sum(left[row * 4 + index] * right[index * 4 + column] for index in range(4))
            if not math.isfinite(value):
                raise OverflowError("matrix cycle produced a non-finite intermediate")
            output.append(value)
    return output


def _identity_error(matrix: Sequence[float]) -> float:
    return max(abs(matrix[row * 4 + column] - (1 if row == column else 0)) for row in range(4) for column in range(4))


def _linear_norm(matrix: Sequence[float]) -> float:
    return max(sum(abs(matrix[row * 4 + column]) for column in range(3)) for row in range(3))


def transform_bounds_canary(
    matrix: Sequence[float],
    inverse_matrix: Sequence[float],
    lower: Point,
    upper: Point,
    reflection_allowed: bool = False,
    round_trip_tolerance: float = 1e-9,
) -> Dict[str, Any]:
    for label, candidate in (("matrix", matrix), ("inverse matrix", inverse_matrix)):
        if len(candidate) != 16 or not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in candidate):
            raise ValueError("transform %s needs 16 finite numeric row-major values" % label)
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in lower + upper):
        raise ValueError("transform bounds need six finite numeric values")
    if not isinstance(round_trip_tolerance, (int, float)) or isinstance(round_trip_tolerance, bool) or not math.isfinite(float(round_trip_tolerance)) or round_trip_tolerance <= 0:
        raise ValueError("round-trip tolerance must be a positive finite number")
    if any(a > b for a, b in zip(lower, upper)):
        raise ValueError("bounds minimum exceeds maximum")
    homogeneous_ok = all(
        float(candidate[index]) == expected
        for candidate in (matrix, inverse_matrix)
        for index, expected in zip((12, 13, 14, 15), (0, 0, 0, 1))
    )
    determinant = determinant3(matrix)
    scale = _linear_norm(matrix)
    inverse_scale = _linear_norm(inverse_matrix)
    if not all(math.isfinite(value) for value in (determinant, scale, inverse_scale)):
        raise OverflowError("transform determinant or norm produced a non-finite value")
    nonsingular = scale > 0 and abs(determinant) > 1e-12 * scale**3
    condition_number = scale * inverse_scale
    if not math.isfinite(condition_number):
        raise OverflowError("transform condition estimate produced a non-finite value")
    conditioning_ok = condition_number <= 1e12
    cycle_error = max(_identity_error(_matrix_product(matrix, inverse_matrix)), _identity_error(_matrix_product(inverse_matrix, matrix)))
    corners = [transform_point(matrix, point) for point in itertools.product(*zip(lower, upper))]
    round_trip_errors = []
    for source_point, transformed_point in zip(itertools.product(*zip(lower, upper)), corners):
        recovered = transform_point(inverse_matrix, transformed_point)
        error = math.dist(recovered, source_point)
        if not math.isfinite(error):
            raise OverflowError("round-trip canary produced non-finite error")
        round_trip_errors.append(error)
    round_trip_max = max(round_trip_errors)
    transformed_min = [min(point[axis] for point in corners) for axis in range(3)]
    transformed_max = [max(point[axis] for point in corners) for axis in range(3)]
    reflection_documented = determinant >= 0 or reflection_allowed
    return {
        "ok": homogeneous_ok and nonsingular and conditioning_ok and cycle_error <= 1e-8 and round_trip_max <= round_trip_tolerance and reflection_documented,
        "layout": "row-major",
        "vector_convention": "column-vector",
        "determinant": determinant,
        "handedness_change": "preserved" if determinant > 0 else "reversed" if determinant < 0 else "singular",
        "reflection_allowed": reflection_allowed,
        "reflection_documented": reflection_documented,
        "homogeneous_last_row_valid": homogeneous_ok,
        "inverse_cycle_max": cycle_error,
        "held_out_count": len(round_trip_errors),
        "round_trip_max": round_trip_max,
        "round_trip_tolerance": round_trip_tolerance,
        "conditioning": {
            "norm": "infinity",
            "condition_number": condition_number,
            "reciprocal_condition": 1.0 / condition_number if condition_number > 0 and math.isfinite(condition_number) else 0.0,
            "acceptable": conditioning_ok,
        },
        "source_bounds": {"min": list(lower), "max": list(upper)},
        "transformed_bounds": {"min": transformed_min, "max": transformed_max},
        "corner_count": len(corners),
    }


def _percentile(sorted_values: Sequence[float], percentile: float) -> float:
    if not sorted_values:
        raise ValueError("cannot compute percentile of empty distances")
    if not isinstance(percentile, (int, float)) or isinstance(percentile, bool) or not math.isfinite(float(percentile)) or not 0 < percentile <= 100:
        raise ValueError("percentiles must be in (0, 100]")
    integer_percentile = int(percentile)
    if float(integer_percentile) == float(percentile):
        lower, remainder = divmod((len(sorted_values) - 1) * integer_percentile, 100)
        upper = lower + (1 if remainder else 0)
        fraction = remainder / 100.0
    else:
        position = (len(sorted_values) - 1) * percentile / 100.0
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        fraction = position - lower
    if lower == upper:
        return sorted_values[lower]
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def realizability_certificate(
    sorted_values: Sequence[float],
    threshold: float,
    percentiles: Sequence[float] = REALIZABILITY_PERCENTILES,
) -> Dict[str, Any]:
    """Summarize a sorted nonnegative sample as a bounded proof certificate.

    Blocks expose every order statistic used by the fixed v1 quantiles and the
    threshold transition.  Normalized moments make certificate verification
    scale-safe without embedding the raw evidence vector.
    """

    if not sorted_values or any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or value < 0
        for value in sorted_values
    ):
        raise ValueError("certificate values must be a nonempty finite nonnegative sequence")
    if any(left > right for left, right in zip(sorted_values, sorted_values[1:])):
        raise ValueError("certificate values must be sorted nondecreasing")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not math.isfinite(float(threshold)) or threshold < 0:
        raise ValueError("certificate threshold must be finite and nonnegative")
    profile = tuple(float(value) for value in percentiles)
    if profile != REALIZABILITY_PERCENTILES:
        raise ValueError("certificate percentiles must be exactly P50, P95, P98, and P99")

    count = len(sorted_values)
    scale = float(sorted_values[-1])
    within_count = bisect_right(sorted_values, threshold)
    boundaries = {0, count, within_count}
    for percentile in REALIZABILITY_PERCENTILES:
        lower, remainder = divmod((count - 1) * int(percentile), 100)
        upper = lower + (1 if remainder else 0)
        boundaries.update((lower, lower + 1, upper, upper + 1))
    ordered_boundaries = sorted(value for value in boundaries if 0 <= value <= count)
    blocks: List[Dict[str, Any]] = []
    for start, stop in zip(ordered_boundaries, ordered_boundaries[1:]):
        if start == stop:
            continue
        raw_values = sorted_values[start:stop]
        if scale == 0:
            normalized = [0.0] * len(raw_values)
        else:
            normalized = [float(value) / scale for value in raw_values]
            if any(value > 0 and ratio == 0 for value, ratio in zip(raw_values, normalized)):
                raise OverflowError("certificate normalization underflowed a nonzero order statistic")
            if any(ratio > 0 and ratio * ratio == 0 for ratio in normalized):
                raise OverflowError("certificate squared normalization underflowed a nonzero order statistic")
        block_sum = math.fsum(normalized)
        block_sum_squares = math.fsum(value * value for value in normalized)
        if not math.isfinite(block_sum) or not math.isfinite(block_sum_squares):
            raise OverflowError("certificate normalized moments are not finite")
        blocks.append(
            {
                "start_index": start,
                "end_index": stop - 1,
                "first": normalized[0],
                "last": normalized[-1],
                "sum": block_sum,
                "sum_squares": block_sum_squares,
                "threshold_class": "within" if stop <= within_count else "outside",
            }
        )
    return {
        "version": "normalized-blocks-v1",
        "scale": scale,
        "blocks": blocks,
    }


def _stdlib_distances(query: Sequence[Point], target: Sequence[Point], batch_size: int) -> List[float]:
    if not target:
        raise ValueError("distance target is empty")
    if len(query) * len(target) > STDLIB_MAX_PAIR_EVALUATIONS // 2:
        raise ValueError(
            "one stdlib distance direction exceeds the hard %d-pair bidirectional work budget; "
            "reduce the deterministic samples or use --backend scipy" % STDLIB_MAX_PAIR_EVALUATIONS
        )
    distances: List[float] = []
    for start in range(0, len(query), batch_size):
        for point in query[start : start + batch_size]:
            best_distance = math.inf
            for candidate in target:
                distance = math.dist(point, candidate)
                if not math.isfinite(distance):
                    raise OverflowError("distance calculation produced a non-finite intermediate")
                if distance < best_distance:
                    best_distance = distance
            distances.append(best_distance)
    return distances


def _scipy_distances(query: Sequence[Point], target: Sequence[Point]) -> List[float]:
    try:
        from scipy.spatial import cKDTree  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("--backend scipy requires an existing scipy installation") from error
    coordinate_scale = max(
        (abs(float(coordinate)) for point in itertools.chain(query, target) for coordinate in point),
        default=0.0,
    )
    if coordinate_scale == 0:
        coordinate_scale = 1.0
    normalized_target = [tuple(coordinate / coordinate_scale for coordinate in point) for point in target]
    normalized_query = [tuple(coordinate / coordinate_scale for coordinate in point) for point in query]
    tree = cKDTree(normalized_target)
    normalized_distances, indices = tree.query(normalized_query, k=1, workers=1)
    distances: List[float] = []
    for query_point, normalized_distance, target_index in zip(query, normalized_distances, indices):
        distance = float(normalized_distance) * coordinate_scale
        exact_selected_distance = math.dist(query_point, target[int(target_index)])
        if not math.isfinite(distance) or not math.isfinite(exact_selected_distance):
            raise OverflowError("scipy distance normalization produced a non-finite magnitude")
        if not math.isclose(distance, exact_selected_distance, rel_tol=1e-12, abs_tol=0.0):
            raise OverflowError("scipy distance normalization lost finite coordinate separation")
        distances.append(exact_selected_distance)
    return distances


def distance_statistics(
    query: Sequence[Point],
    target: Sequence[Point],
    tolerance: float,
    percentiles: Sequence[float],
    batch_size: int,
    backend: str,
) -> Dict[str, Any]:
    if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool) or not math.isfinite(float(tolerance)) or tolerance <= 0:
        raise ValueError("tolerance must be positive")
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
        raise ValueError("batch size must be positive")
    if tuple(float(value) for value in percentiles) != REALIZABILITY_PERCENTILES:
        raise ValueError("percentiles must be exactly P50, P95, P98, and P99 for the v1 evidence certificate")
    for label, points in (("query", query), ("target", target)):
        if not points or any(len(point) != 3 or not all(math.isfinite(float(value)) for value in point) for point in points):
            raise ValueError("distance %s points must be nonempty finite XYZ triples" % label)
    if backend == "stdlib":
        distances = _stdlib_distances(query, target, batch_size)
        backend_name = "stdlib-bounded"
    elif backend == "scipy":
        distances = _scipy_distances(query, target)
        backend_name = "scipy-ckdtree"
    else:
        raise ValueError("backend must be stdlib or scipy")
    if len(distances) != len(query) or any(not math.isfinite(value) or value < 0 for value in distances):
        raise OverflowError("distance backend returned non-finite or negative magnitudes")
    ordered = sorted(distances)
    distance_scale = ordered[-1]
    if distance_scale == 0:
        mean = 0.0
        rms = 0.0
    else:
        normalized = [value / distance_scale for value in distances]
        mean = distance_scale * (math.fsum(normalized) / len(normalized))
        rms = distance_scale * math.sqrt(
            math.fsum(value * value for value in normalized) / len(normalized)
        )
        if mean == 0 or rms == 0:
            raise OverflowError("nonzero distance moments underflow the supported summary precision")
    if not math.isfinite(mean) or not math.isfinite(rms):
        raise OverflowError("distance summary produced a non-finite statistic")
    normalized_ordered = [0.0] * len(ordered) if distance_scale == 0 else [value / distance_scale for value in ordered]
    percentile_results = []
    for percentile in REALIZABILITY_PERCENTILES:
        normalized_quantile = _percentile(normalized_ordered, percentile)
        quantile = distance_scale * normalized_quantile
        if normalized_quantile > 0 and quantile == 0:
            raise OverflowError("nonzero distance percentile underflowed the supported summary precision")
        percentile_results.append({"percentile": percentile, "distance": quantile})
    return {
        "metric_kind": "point-to-point",
        "signedness": "unsigned",
        "evaluated_count": len(distances),
        "target_count": len(target),
        "tolerance": tolerance,
        "within_tolerance_percent": 100.0 * sum(value <= tolerance for value in distances) / len(distances),
        "mean": mean,
        "rms": rms,
        "percentiles": percentile_results,
        "maximum": ordered[-1],
        "realizability_certificate": realizability_certificate(ordered, tolerance),
        "backend": backend_name,
        "batch_size": batch_size,
    }


def bidirectional_distance(
    points_a: Sequence[Point],
    points_b: Sequence[Point],
    tolerance: float,
    percentiles: Sequence[float],
    batch_size: int,
    backend: str = "stdlib",
) -> Dict[str, Any]:
    if len(points_a) > MAX_SAMPLE_POINTS or len(points_b) > MAX_SAMPLE_POINTS:
        raise ValueError("distance input exceeds the hard %d-point per-cloud cap" % MAX_SAMPLE_POINTS)
    if backend == "stdlib" and 2 * len(points_a) * len(points_b) > STDLIB_MAX_PAIR_EVALUATIONS:
        raise ValueError(
            "bidirectional stdlib canary would evaluate %d pairs, above the hard %d-pair work budget; "
            "reduce the deterministic samples or use --backend scipy"
            % (2 * len(points_a) * len(points_b), STDLIB_MAX_PAIR_EVALUATIONS)
        )
    return {
        "metric_scope": "bounded-point-sample-canary",
        "limitations": [
            "point-to-point evidence does not establish point-to-analytic-surface distance",
            "sampled reverse distance does not establish coverage of unobserved CAD closure faces",
        ],
        "directions": [
            {"direction": "a-to-b", **distance_statistics(points_a, points_b, tolerance, percentiles, batch_size, backend)},
            {"direction": "b-to-a", **distance_statistics(points_b, points_a, tolerance, percentiles, batch_size, backend)},
        ],
    }
