#!/usr/bin/env python3
"""Validate a versioned point-cloud feature contract without dependencies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from pcre_tools.contract import SCHEMA_ID, load_json_strict, validate_contract


SCRIPT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = SCRIPT_DIR.parent / "assets"
SCHEMA_PATH = ASSETS_DIR / "feature-contract.schema.json"
EXAMPLE_PATH = ASSETS_DIR / "feature-contract.example.json"
CONTRACTS_DIR = ASSETS_DIR / "contracts"


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError("invalid command arguments")


def _serialize(report: Dict[str, Any], pretty: bool) -> str:
    return json.dumps(report, indent=2 if pretty else None, sort_keys=True, allow_nan=False) + "\n"


def _self_test() -> Dict[str, Any]:
    cases = [
        ("canonical-example", EXAMPLE_PATH, True, set()),
        ("canonical-valid", CONTRACTS_DIR / "feature-contract.valid.json", True, set()),
        ("invalid-transform", CONTRACTS_DIR / "feature-contract.invalid-transform.json", False, {"transform.homogeneous_row"}),
        ("invalid-authority", CONTRACTS_DIR / "feature-contract.invalid-authority.json", False, {"authority.format", "authority.reopen"}),
    ]
    checks: List[Dict[str, Any]] = []
    schema = load_json_strict(SCHEMA_PATH)
    schema_ok = isinstance(schema, dict) and schema.get("$id") == SCHEMA_ID and schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    checks.append({"id": "schema-identity", "ok": schema_ok})
    for case_id, path, expected_ok, expected_codes in cases:
        result = validate_contract(load_json_strict(path))
        actual_codes = {item["code"] for item in result["errors"]}
        passed = result["ok"] is expected_ok and expected_codes.issubset(actual_codes)
        checks.append(
            {
                "id": case_id,
                "ok": passed,
                "expected_valid": expected_ok,
                "actual_valid": result["ok"],
                "expected_error_codes": sorted(expected_codes),
                "actual_error_codes": sorted(actual_codes),
            }
        )
    return {
        "ok": all(check["ok"] for check in checks),
        "mode": "self-test",
        "schema_id": SCHEMA_ID,
        "checks": checks,
    }


def main(argv: List[str] | None = None) -> int:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("contract", nargs="?", type=Path, help="feature-contract JSON file")
    parser.add_argument("--self-test", action="store_true", help="validate bundled positive and negative canaries")
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")
    try:
        args = parser.parse_args(argv)
    except ValueError as error:
        sys.stdout.write(
            _serialize(
                {"ok": False, "contract_valid": False, "evidence_status": "not-evaluated", "error_count": 1,
                 "errors": [{"level": "error", "code": "argument_error", "path": "", "message": str(error)}]},
                False,
            )
        )
        return 2
    if args.self_test:
        if args.contract is not None:
            sys.stdout.write(
                _serialize(
                    {"ok": False, "contract_valid": False, "evidence_status": "not-evaluated", "error_count": 1,
                     "errors": [{"level": "error", "code": "argument_error", "path": "", "message": "invalid command arguments"}]},
                    args.pretty,
                )
            )
            return 2
        try:
            report = _self_test()
            payload = _serialize(report, args.pretty)
        except (OSError, ValueError, ArithmeticError, TypeError, UnicodeError, json.JSONDecodeError, RecursionError):
            report = {"ok": False, "mode": "self-test", "error": {"code": "io_or_json", "message": "bundled self-test asset could not be loaded or validated"}}
            sys.stdout.write(_serialize(report, args.pretty))
            return 2
        sys.stdout.write(payload)
        return 0 if report["ok"] else 1
    if args.contract is None:
        sys.stdout.write(
            _serialize(
                {"ok": False, "contract_valid": False, "evidence_status": "not-evaluated", "error_count": 1,
                 "errors": [{"level": "error", "code": "argument_error", "path": "", "message": "invalid command arguments"}]},
                args.pretty,
            )
        )
        return 2
    try:
        contract = load_json_strict(args.contract)
        report = validate_contract(contract)
        payload = _serialize(report, args.pretty)
    except (OSError, ValueError, ArithmeticError, TypeError, UnicodeError, json.JSONDecodeError, RecursionError) as error:
        message = str(error).replace(str(args.contract), "<contract>")
        payload = _serialize(
            {"ok": False, "contract_valid": False, "evidence_status": "not-evaluated", "error_count": 1,
             "errors": [{"level": "error", "code": "io_or_json", "path": "", "message": message}]},
            args.pretty,
        )
        sys.stdout.write(payload)
        return 2
    sys.stdout.write(payload)
    if any(item.get("code") == "schema.resource_budget" for item in report.get("errors", [])):
        return 2
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
