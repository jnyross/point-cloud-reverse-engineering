#!/usr/bin/env python3
"""Create deterministic point-cloud identities, samples, and bounded canaries."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from pcre_tools.cloud import (
    CloudFormatError,
    analyze_cloud,
    bidirectional_distance,
    load_mask,
    scan_and_sample,
    transform_bounds_canary,
    write_xyz,
)


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError("invalid command arguments")


def _serialize(value: Dict[str, Any], pretty: bool) -> str:
    return json.dumps(value, indent=2 if pretty else None, sort_keys=True, allow_nan=False) + "\n"


def _redact_error(error: BaseException, args: argparse.Namespace) -> str:
    message = str(error)
    for candidate in vars(args).values():
        if isinstance(candidate, Path):
            message = message.replace(str(candidate), "<path>")
    # Errors from atomic publication can mention a random same-directory temp.
    message = re.sub(r"(?<![A-Za-z0-9])/(?:[^\s'\":,;]+/?)+", "<path>", message)
    message = re.sub(r"(?i)(?<![A-Za-z0-9])[a-z]:[\\/][^\s'\":,;]+", "<path>", message)
    message = re.sub(r"(?:\\\\|//)[^\s'\":,;]+", "<path>", message)
    return message


def _add_input_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("auto", "xyz", "ply"), default="auto")
    parser.add_argument("--skip-lines", type=int, default=0)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fingerprint = subparsers.add_parser("fingerprint", help="hash, count, and bound an immutable point cloud")
    fingerprint.add_argument("cloud", type=Path)
    _add_input_options(fingerprint)

    sample = subparsers.add_parser("sample", help="write a deterministic, role-separated hash-rank sample")
    sample.add_argument("cloud", type=Path)
    sample.add_argument("--role", choices=("measurement", "display"), required=True)
    sample.add_argument("--count", type=int, required=True)
    sample.add_argument("--seed", type=int, default=0)
    sample.add_argument("--mask", type=Path)
    sample.add_argument("--frame", required=True, help="frame of the source points and any mask")
    sample.add_argument("--output", type=Path, required=True)
    sample.add_argument("--overwrite", action="store_true", help="explicitly replace an existing derived sample")
    _add_input_options(sample)

    transform = subparsers.add_parser("transform-canary", help="check row-major transform semantics and map all AABB corners")
    transform.add_argument("--matrix", type=float, nargs=16, metavar="M", required=True)
    transform.add_argument("--inverse-matrix", type=float, nargs=16, metavar="I", required=True)
    transform.add_argument("--bounds", type=float, nargs=6, metavar=("MIN_X", "MIN_Y", "MIN_Z", "MAX_X", "MAX_Y", "MAX_Z"), required=True)
    transform.add_argument("--reflection-allowed", action="store_true")
    transform.add_argument("--round-trip-tolerance", type=float, default=1e-9)

    distance = subparsers.add_parser("distance", help="bounded masked bidirectional point-to-point canary")
    distance.add_argument("cloud_a", type=Path)
    distance.add_argument("cloud_b", type=Path)
    distance.add_argument("--format-a", choices=("auto", "xyz", "ply"), default="auto")
    distance.add_argument("--format-b", choices=("auto", "xyz", "ply"), default="auto")
    distance.add_argument("--skip-lines-a", type=int, default=0)
    distance.add_argument("--skip-lines-b", type=int, default=0)
    distance.add_argument("--mask-a", type=Path)
    distance.add_argument("--mask-b", type=Path)
    distance.add_argument("--max-a", type=int, default=2000)
    distance.add_argument("--max-b", type=int, default=2000)
    distance.add_argument("--seed", type=int, default=0)
    distance.add_argument("--batch-size", type=int, default=256)
    distance.add_argument("--tolerance", type=float, required=True)
    distance.add_argument("--percentiles", type=float, nargs="+", default=(50.0, 95.0, 98.0, 99.0))
    distance.add_argument("--backend", choices=("stdlib", "scipy"), default="stdlib")
    distance.add_argument("--frame", required=True, help="shared frame identifier; no implicit registration is performed")
    return parser


def run(args: argparse.Namespace) -> Dict[str, Any]:
    if args.command == "fingerprint":
        return {
            "operation_ok": True,
            "evidence_status": "not-evaluated",
            "operation": "fingerprint",
            **analyze_cloud(args.cloud, args.format, args.skip_lines),
        }
    if args.command == "sample":
        if args.count < 1 or args.seed < 0 or args.skip_lines < 0:
            raise ValueError("count must be positive; seed and skip-lines must be nonnegative")
        mask, mask_hash = load_mask(args.mask)
        report, points = scan_and_sample(
            args.cloud, args.count, args.seed, args.role,
            input_format=args.format, skip_lines=args.skip_lines, mask=mask, frame=args.frame,
        )
        artifact = write_xyz(args.output, points, overwrite=args.overwrite, source_path=args.cloud)
        return {
            "operation_ok": True,
            "evidence_status": "not-evaluated",
            "operation": "sample",
            "mask_sha256": mask_hash,
            **report,
            "sample_artifact": {**artifact, "format": "xyz"},
        }
    if args.command == "transform-canary":
        lower = (args.bounds[0], args.bounds[1], args.bounds[2])
        upper = (args.bounds[3], args.bounds[4], args.bounds[5])
        canary = transform_bounds_canary(
            args.matrix, args.inverse_matrix, lower, upper,
            reflection_allowed=args.reflection_allowed,
            round_trip_tolerance=args.round_trip_tolerance,
        )
        passed = bool(canary.pop("ok"))
        return {
            "operation_ok": True,
            "evidence_status": "pass" if passed else "fail",
            "operation": "transform-canary",
            **canary,
        }
    if args.command == "distance":
        if args.max_a < 1 or args.max_b < 1 or args.seed < 0 or args.skip_lines_a < 0 or args.skip_lines_b < 0:
            raise ValueError("sample limits must be positive; seed and skip-lines must be nonnegative")
        mask_a, mask_a_hash = load_mask(args.mask_a)
        mask_b, mask_b_hash = load_mask(args.mask_b)
        report_a, points_a = scan_and_sample(
            args.cloud_a, args.max_a, args.seed, "distance-a",
            input_format=args.format_a, skip_lines=args.skip_lines_a, mask=mask_a, frame=args.frame,
        )
        report_b, points_b = scan_and_sample(
            args.cloud_b, args.max_b, args.seed, "distance-b",
            input_format=args.format_b, skip_lines=args.skip_lines_b, mask=mask_b, frame=args.frame,
        )
        evidence = bidirectional_distance(
            points_a, points_b, args.tolerance, args.percentiles,
            args.batch_size, backend=args.backend,
        )
        estimated_bytes = (len(points_a) + len(points_b)) * 3 * 8 + max(len(points_a), len(points_b)) * 8
        return {
            "operation_ok": True,
            "evidence_status": "not-evaluated",
            "operation": "distance",
            "frame": args.frame,
            "registration_performed": False,
            "cloud_a": report_a,
            "cloud_b": report_b,
            "mask_a_sha256": mask_a_hash,
            "mask_b_sha256": mask_b_hash,
            "estimated_numeric_working_set_mib": estimated_bytes / (1024 * 1024),
            **evidence,
        }
    raise AssertionError("unreachable command")


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except ValueError as error:
        sys.stdout.write(
            _serialize(
                {
                    "operation_ok": False,
                    "evidence_status": "not-evaluated",
                    "error": {"code": "argument_error", "message": str(error)},
                },
                False,
            )
        )
        return 2
    try:
        result = run(args)
        payload = _serialize(result, args.pretty)
    except (OSError, ValueError, ArithmeticError, UnicodeError, CloudFormatError, RuntimeError, json.JSONDecodeError) as error:
        payload = _serialize(
            {
                "operation_ok": False,
                "evidence_status": "not-evaluated",
                "error": {"code": "evidence_error", "message": _redact_error(error, args)},
            },
            args.pretty,
        )
        sys.stdout.write(payload)
        return 2
    sys.stdout.write(payload)
    if not result.get("operation_ok"):
        return 2
    return 1 if result.get("evidence_status") == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
