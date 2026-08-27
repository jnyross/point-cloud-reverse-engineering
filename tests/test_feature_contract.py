from __future__ import annotations

import copy
import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "point-cloud-reverse-engineering"
SCRIPTS = SKILL / "scripts"
ASSETS = SKILL / "assets"
sys.path.insert(0, str(SCRIPTS))

from pcre_tools.contract import canonical_json_sha256, load_json_strict, validate_contract  # noqa: E402
import pcre_tools.contract as contract_tools  # noqa: E402
from pcre_tools.cloud import realizability_certificate  # noqa: E402
from pcre_tools.schema_subset import MAX_INSTANCE_NODES, check_supported_schema, validate_instance  # noqa: E402


class FeatureContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.valid = load_json_strict(ASSETS / "feature-contract.example.json")
        cls.schema = load_json_strict(ASSETS / "feature-contract.schema.json")

    def _set_all_claims(self, contract: dict, status: str) -> None:
        for result in contract["validation"]["results"]:
            result["acceptance_status"] = status

    def _set_normal_gates(self, result: dict, mean: float = 5, p95: float = 10, maximum: float = 15) -> None:
        result["acceptance_criteria"].update(
            {
                "maximum_normal_mean_angle_deg": mean,
                "maximum_normal_p95_angle_deg": p95,
                "maximum_normal_angle_deg": maximum,
            }
        )

    def _set_distance_evidence(self, result: dict, distances: list[float]) -> None:
        ordered = sorted(distances)
        count = len(ordered)
        result["eligible_count"] = count
        result["evaluated_count"] = count
        result["within_tolerance_percent"] = 100 * sum(
            value <= result["tolerance"] for value in ordered
        ) / count
        result["mean"] = math.fsum(ordered) / count
        result["rms"] = math.hypot(*ordered) / math.sqrt(count)
        result["maximum"] = ordered[-1]
        result["percentiles"] = []
        for percentile in (50, 95, 98, 99):
            numerator = (count - 1) * percentile
            lower, remainder = divmod(numerator, 100)
            upper = lower + (1 if remainder else 0)
            fraction = remainder / 100
            distance = ordered[lower] if lower == upper else math.fsum(
                ((1 - fraction) * ordered[lower], fraction * ordered[upper])
            )
            result["percentiles"].append({"percentile": percentile, "distance": distance})
        result["realizability_certificate"] = realizability_certificate(
            ordered, result["tolerance"]
        )

    def _set_required_normal_evidence(
        self,
        result: dict,
        angles: list[float],
        threshold: float = 15,
    ) -> None:
        ordered = sorted(angles)
        count = len(ordered)
        lower, remainder = divmod((count - 1) * 95, 100)
        upper = lower + (1 if remainder else 0)
        fraction = remainder / 100
        p95 = ordered[lower] if lower == upper else math.fsum(
            ((1 - fraction) * ordered[lower], fraction * ordered[upper])
        )
        result["normal_agreement"] = {
            "applicability": "required",
            "source_normal_quality": "verified",
            "quality_evidence": "unit normal audit",
            "evaluated_count": count,
            "mean_angle_deg": math.fsum(ordered) / count,
            "p95_angle_deg": p95,
            "maximum_angle_deg": ordered[-1],
            "angle_threshold_deg": threshold,
            "exceeding_count": sum(value > threshold for value in ordered),
            "realizability_certificate": realizability_certificate(ordered, threshold),
        }

    def _assert_valid_diagnostic(self, contract: dict, status: str) -> dict:
        report = validate_contract(contract)
        self.assertTrue(report["contract_valid"], report)
        self.assertEqual(report["evidence_status"], status, report)
        self.assertEqual(report["ok"], status == "pass", report)
        return report

    def test_example_passes_stdlib_semantic_validator(self) -> None:
        report = validate_contract(copy.deepcopy(self.valid))
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["error_count"], 0)

    def test_example_passes_formal_schema_when_jsonschema_is_available(self) -> None:
        if importlib.util.find_spec("jsonschema") is None:
            self.skipTest("optional jsonschema package is unavailable")
        from jsonschema import Draft202012Validator

        schema = load_json_strict(ASSETS / "feature-contract.schema.json")
        Draft202012Validator.check_schema(schema)
        errors = list(Draft202012Validator(schema).iter_errors(self.valid))
        self.assertEqual(errors, [])

    def test_canonical_negative_fixtures_fail_for_expected_reasons(self) -> None:
        transform = validate_contract(load_json_strict(ASSETS / "contracts" / "feature-contract.invalid-transform.json"))
        authority = validate_contract(load_json_strict(ASSETS / "contracts" / "feature-contract.invalid-authority.json"))
        self.assertFalse(transform["ok"])
        self.assertFalse(transform["contract_valid"])
        self.assertIn("transform.homogeneous_row", {item["code"] for item in transform["errors"]})
        self.assertFalse(authority["ok"])
        self.assertFalse(authority["contract_valid"])
        self.assertTrue({"authority.format", "authority.reopen"}.issubset({item["code"] for item in authority["errors"]}))

    def test_private_path_and_stale_mask_hash_are_rejected(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["frames"][0]["origin"] = "/" + "ho" + "me/private/incoming/customer-scan.xyz"
        contract["masks"][0]["definition"]["max"][0] = 99
        report = validate_contract(contract)
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("privacy.absolute_path", codes)
        self.assertIn("lineage.mask_hash", codes)

    def test_changed_parameter_requires_regularization_reason(self) -> None:
        contract = copy.deepcopy(self.valid)
        del contract["parameters"][0]["regularization_reason"]
        report = validate_contract(contract)
        self.assertIn("parameter.regularization_reason", {item["code"] for item in report["errors"]})

    def test_kernel_tier_and_semantic_metric_consistency_are_checked(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["authority"]["independent_reopen"]["validation_tier"] = "cross-kernel"
        report = validate_contract(contract)
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("authority.kernel_lineage", codes)

        signed = copy.deepcopy(self.valid)
        signed["validation"]["results"][0]["signedness"] = "signed"
        signed_report = validate_contract(signed)
        self.assertIn("schema.const", {item["code"] for item in signed_report["errors"]})

    def test_normal_applicability_cannot_overclaim_xyz_source(self) -> None:
        contract = copy.deepcopy(self.valid)
        self._set_required_normal_evidence(contract["validation"]["results"][0], [0, 0, 0, 1, 1, 1, 2, 3])
        normal = contract["validation"]["results"][0]["normal_agreement"]
        normal["quality_evidence"] = "unit normals checked against the scanner export"
        self._set_normal_gates(contract["validation"]["results"][0])
        report = validate_contract(contract)
        self.assertIn("validation.normal_source", {item["code"] for item in report["errors"]})

    def test_mask_digest_is_canonical_json(self) -> None:
        mask = self.valid["masks"][0]
        self.assertEqual(mask["definition_sha256"], canonical_json_sha256(mask["definition"]))

    def test_global_and_feature_local_results_have_distinct_bidirectional_scopes(self) -> None:
        results = self.valid["validation"]["results"]
        self.assertEqual(len(results), 4)
        self.assertTrue(all(len(result["mask_ids"]) == 1 for result in results))
        pairs = {(result["mask_ids"][0], result["direction"]) for result in results}
        self.assertEqual(
            pairs,
            {
                ("global-fit", "cloud-to-authority"), ("global-fit", "authority-to-cloud"),
                ("critical-body", "cloud-to-authority"), ("critical-body", "authority-to-cloud"),
            },
        )
        critical = next(mask for mask in self.valid["masks"] if mask["id"] == "critical-body")
        global_mask = next(mask for mask in self.valid["masks"] if mask["id"] == "global-fit")
        self.assertEqual(critical["feature_id"], "body-envelope")
        self.assertNotEqual(critical["definition_sha256"], global_mask["definition_sha256"])

        identical = copy.deepcopy(self.valid)
        global_mask = next(mask for mask in identical["masks"] if mask["id"] == "global-fit")
        critical = next(mask for mask in identical["masks"] if mask["id"] == "critical-body")
        critical["definition"] = copy.deepcopy(global_mask["definition"])
        critical["definition_sha256"] = canonical_json_sha256(critical["definition"])
        self.assertIn("mask.critical_scope", {item["code"] for item in validate_contract(identical)["errors"]})

        for numeric_variant in (0.0, -0.0):
            with self.subTest(numeric_variant=numeric_variant):
                numerically_identical = copy.deepcopy(self.valid)
                global_mask = next(mask for mask in numerically_identical["masks"] if mask["id"] == "global-fit")
                critical = next(mask for mask in numerically_identical["masks"] if mask["id"] == "critical-body")
                if math.copysign(1.0, numeric_variant) < 0:
                    global_mask["definition"]["min"][0] = 0
                    global_mask["definition_sha256"] = canonical_json_sha256(global_mask["definition"])
                critical["definition"] = copy.deepcopy(global_mask["definition"])
                critical["definition"]["min"][0] = numeric_variant if math.copysign(1.0, numeric_variant) < 0 else 10.0
                critical["definition_sha256"] = canonical_json_sha256(critical["definition"])
                self.assertNotEqual(critical["definition_sha256"], global_mask["definition_sha256"])
                numeric_codes = {item["code"] for item in validate_contract(numerically_identical)["errors"]}
                self.assertIn("mask.critical_scope", numeric_codes)

    def test_critical_mask_feature_and_global_count_lineage_are_enforced(self) -> None:
        wrong_feature = copy.deepcopy(self.valid)
        wrong_feature["components"][0]["included_features"].append("unrelated-port")
        wrong_feature["validation"]["results"][2]["semantic_target"]["feature_id"] = "unrelated-port"
        self.assertIn("lineage.mask_feature", {item["code"] for item in validate_contract(wrong_feature)["errors"]})

        cherry_pick = copy.deepcopy(self.valid)
        cherry_pick["validation"]["results"][0]["eligible_count"] = 1
        cherry_pick["validation"]["results"][0]["evaluated_count"] = 1
        self.assertIn("validation.global_count", {item["code"] for item in validate_contract(cherry_pick)["errors"]})

    def test_v1_contract_cannot_leave_a_second_component_unvalidated(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["components"].append(
            {
                "id": "unvalidated-addon",
                "frame": "cad",
                "authority_sha256": contract["authority"]["artifact"]["sha256"],
                "primitive_chain": ["separate-solid"],
                "included_features": ["addon-envelope"],
                "excluded_features": [],
            }
        )
        structural = validate_contract(contract)
        self.assertIn("schema.max_items", {item["code"] for item in structural["errors"]})
        semantic_defense = validate_contract(contract, schema=True)
        self.assertIn("component.contract_scope", {item["code"] for item in semantic_defense["errors"]})
        if importlib.util.find_spec("jsonschema") is not None:
            from jsonschema import Draft202012Validator
            self.assertTrue(list(Draft202012Validator(self.schema).iter_errors(contract)))

    def test_required_accuracy_percentile_profile_cannot_be_weakened(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["validation"]["requirements"]["required_percentiles"].remove(99)
        report = validate_contract(contract)
        self.assertFalse(report["contract_valid"])
        self.assertIn("schema.min_items", {item["code"] for item in report["errors"]})

    def test_external_route_point_formats_remain_valid_contract_evidence(self) -> None:
        artifact_paths = (
            ("source", "artifact"),
            ("samples", "measurement", "artifact"),
            ("authority", "validation_sample", "artifact"),
        )
        for artifact_format in ("e57", "las", "laz"):
            for path in artifact_paths:
                with self.subTest(format=artifact_format, path=path):
                    contract = copy.deepcopy(self.valid)
                    value = contract
                    for token in path:
                        value = value[token]
                    value["format"] = artifact_format
                    self._assert_valid_diagnostic(contract, "pass")

    def test_portable_tokens_reject_trailing_newlines(self) -> None:
        mutations = (
            lambda contract: contract["samples"]["measurement"].__setitem__("algorithm_version", "pcre-tools-1.0\n"),
            lambda contract: contract["authority"]["validation_sample"]["derivation"].__setitem__("algorithm_version", "cad-sampler-1.0\n"),
            lambda contract: contract["source"]["artifact"].__setitem__("media_type", "text/plain\n"),
            lambda contract: contract["source"]["artifact"].__setitem__("sha256", ("a" * 64) + "\n"),
        )
        for mutate in mutations:
            contract = copy.deepcopy(self.valid)
            mutate(contract)
            self.assertFalse(validate_contract(contract)["contract_valid"])

    def test_acceptance_zero_percent_is_a_valid_recorded_failure_not_a_false_green(self) -> None:
        contract = copy.deepcopy(self.valid)
        result = contract["validation"]["results"][0]
        self._set_distance_evidence(result, [0.201, 0.202, 0.203, 0.204, 0.205, 0.206, 0.207, 0.21])
        result["acceptance_status"] = "fail"
        report = self._assert_valid_diagnostic(contract, "fail")
        self.assertIn("within-tolerance percentage below minimum", report["evidence_results"][0]["reasons"])

    def test_acceptance_maximum_and_percentile_failures_are_derived(self) -> None:
        maximum_contract = copy.deepcopy(self.valid)
        maximum_result = maximum_contract["validation"]["results"][0]
        self._set_distance_evidence(maximum_result, [0, 0.01, 0.02, 0.025, 0.03, 0.04, 0.06, 0.16])
        maximum_result["acceptance_status"] = "fail"
        maximum_report = self._assert_valid_diagnostic(maximum_contract, "fail")
        self.assertIn("maximum distance above gate", maximum_report["evidence_results"][0]["reasons"])

        percentile_contract = copy.deepcopy(self.valid)
        percentile_result = percentile_contract["validation"]["results"][0]
        self._set_distance_evidence(percentile_result, [0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.08, 0.12])
        percentile_result["acceptance_status"] = "fail"
        percentile_report = self._assert_valid_diagnostic(percentile_contract, "fail")
        self.assertIn("P95 distance above gate", percentile_report["evidence_results"][0]["reasons"])

    def test_equal_or_sub_uncertainty_tolerance_is_inconclusive(self) -> None:
        expanded = self.valid["uncertainty"]["expanded_uncertainty"]
        for tolerance in (expanded, 0.1):
            with self.subTest(tolerance=tolerance):
                contract = copy.deepcopy(self.valid)
                for result in contract["validation"]["results"]:
                    result["tolerance"] = tolerance
                    self._set_distance_evidence(result, [tolerance * 0.4] * result["evaluated_count"])
                    result["acceptance_status"] = "inconclusive"
                report = self._assert_valid_diagnostic(contract, "inconclusive")
                self.assertTrue(all("tolerance is not above expanded uncertainty" in row["reasons"] for row in report["evidence_results"]))

    def test_provisional_and_unknown_units_force_inconclusive(self) -> None:
        for status in ("provisional", "unknown"):
            with self.subTest(status=status):
                contract = copy.deepcopy(self.valid)
                contract["source"]["units_status"] = status
                self._set_all_claims(contract, "inconclusive")
                report = self._assert_valid_diagnostic(contract, "inconclusive")
                self.assertTrue(
                    all(any("source units are not verified" in reason for reason in row["reasons"]) for row in report["evidence_results"])
                )

    def test_provisional_units_make_physical_threshold_failure_inconclusive(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["source"]["units_status"] = "provisional"
        self._set_distance_evidence(
            contract["validation"]["results"][0],
            [0.201, 0.202, 0.203, 0.204, 0.205, 0.206, 0.207, 0.21],
        )
        self._set_all_claims(contract, "inconclusive")
        self._assert_valid_diagnostic(contract, "inconclusive")

    def test_dimensionless_coverage_failure_is_not_hidden_by_provisional_units(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["source"]["units_status"] = "provisional"
        result = contract["validation"]["results"][0]
        result["completeness"] = "partial-observed"
        result["unobserved_face_treatment"] = "separately-reported"
        result["observed_coverage_percent"] = 1
        result["acceptance_status"] = "fail"
        for other in contract["validation"]["results"][1:]:
            other["acceptance_status"] = "inconclusive"
        report = self._assert_valid_diagnostic(contract, "fail")
        self.assertIn("observed coverage percentage below minimum", report["evidence_results"][0]["reasons"])

    def test_partial_coverage_and_point_metric_for_analytic_surface_are_inconclusive(self) -> None:
        partial = copy.deepcopy(self.valid)
        result = partial["validation"]["results"][0]
        result["completeness"] = "partial-observed"
        result["unobserved_face_treatment"] = "separately-reported"
        result["observed_coverage_percent"] = 0.001
        result["acceptance_criteria"]["minimum_observed_coverage_percent"] = 0
        result["acceptance_status"] = "inconclusive"
        partial_report = self._assert_valid_diagnostic(partial, "inconclusive")
        self.assertIn("semantic target is not completely observed", partial_report["evidence_results"][0]["reasons"])

        analytic = copy.deepcopy(self.valid)
        analytic["validation"]["results"][0]["metric_kind"] = "point-to-point"
        analytic["validation"]["results"][0]["acceptance_status"] = "inconclusive"
        analytic_report = self._assert_valid_diagnostic(analytic, "inconclusive")
        self.assertIn("point-to-point evidence does not validate", analytic_report["evidence_results"][0]["reasons"][0])

    def test_claimed_acceptance_status_must_match_derived_status(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["validation"]["results"][0]["acceptance_status"] = "fail"
        report = validate_contract(contract)
        self.assertFalse(report["contract_valid"])
        self.assertIn("validation.acceptance_claim", {item["code"] for item in report["errors"]})

    def test_within_tolerance_percentage_must_agree_with_recorded_maximum(self) -> None:
        contract = copy.deepcopy(self.valid)
        result = contract["validation"]["results"][0]
        result["maximum"] = result["tolerance"] + 0.01
        result["acceptance_criteria"]["maximum_distance"] = 1
        report = validate_contract(contract)
        self.assertFalse(report["contract_valid"])
        self.assertIn("validation.certificate_scale", {item["code"] for item in report["errors"]})

    def test_percentiles_must_agree_with_within_tolerance_percentage(self) -> None:
        contract = copy.deepcopy(self.valid)
        result = contract["validation"]["results"][0]
        result["within_tolerance_percent"] = 50
        result["acceptance_criteria"]["minimum_within_tolerance_percent"] = 1
        report = validate_contract(contract)
        self.assertIn("validation.certificate_threshold_count", {item["code"] for item in report["errors"]})

        interpolated = copy.deepcopy(self.valid)
        interpolated["validation"]["requirements"]["required_percentiles"] = [50, 51, 95, 98, 99]
        p51_by_id = {
            "cloud-to-step-global": 0.02785,
            "step-to-cloud-global": 0.0357,
            "cloud-to-step-critical": 0.0306,
            "step-to-cloud-critical": 0.0406,
        }
        for item in interpolated["validation"]["results"]:
            item["percentiles"].insert(1, {"percentile": 51, "distance": p51_by_id[item["id"]]})
            item["acceptance_criteria"]["percentile_gates"].insert(1, {"percentile": 51, "maximum_distance": 1})
        item = interpolated["validation"]["results"][2]
        item["percentiles"] = [
            {"percentile": 50, "distance": 0.5}, {"percentile": 51, "distance": 0.51},
            {"percentile": 95, "distance": 0.95}, {"percentile": 98, "distance": 0.98},
            {"percentile": 99, "distance": 0.99},
        ]
        item.update(
            {"eligible_count": 2, "evaluated_count": 2, "tolerance": 0.6, "within_tolerance_percent": 50,
             "mean": 0.5, "rms": 2 ** -0.5, "maximum": 1}
        )
        item["acceptance_criteria"]["minimum_within_tolerance_percent"] = 1
        item["acceptance_criteria"]["maximum_distance"] = 1
        for gate in item["acceptance_criteria"]["percentile_gates"]:
            gate["maximum_distance"] = 1
        interpolated_report = validate_contract(interpolated)
        self.assertFalse(interpolated_report["contract_valid"])
        self.assertIn("schema.max_items", {item["code"] for item in interpolated_report["errors"]})

    def test_distance_moments_must_be_mathematically_realizable(self) -> None:
        contract = copy.deepcopy(self.valid)
        result = contract["validation"]["results"][0]
        result["mean"] = 0.001
        result["rms"] = 0.1
        result["maximum"] = 0.1
        report = validate_contract(contract)
        self.assertIn("validation.moment_consistency", {item["code"] for item in report["errors"]})

        tiny = copy.deepcopy(self.valid)
        result = tiny["validation"]["results"][0]
        result["mean"] = 1e-300
        result["rms"] = 1e-13
        result["maximum"] = 1e-10
        for percentile in result["percentiles"]:
            percentile["distance"] = 0
        tiny_report = validate_contract(tiny)
        self.assertIn("validation.moment_consistency", {item["code"] for item in tiny_report["errors"]})

        zero_moments = copy.deepcopy(self.valid)
        result = zero_moments["validation"]["results"][0]
        result["mean"] = 0
        result["rms"] = 0
        self.assertEqual(validate_instance(zero_moments, self.schema), [])
        zero_report = validate_contract(zero_moments)
        zero_codes = {item["code"] for item in zero_report["errors"]}
        self.assertIn("validation.percentile_mean_bound", zero_codes)
        self.assertIn("validation.percentile_rms_bound", zero_codes)
        if importlib.util.find_spec("jsonschema") is not None:
            from jsonschema import Draft202012Validator
            self.assertEqual(list(Draft202012Validator(self.schema).iter_errors(zero_moments)), [])

        impossible_rms_ceiling = copy.deepcopy(self.valid)
        impossible_rms_ceiling["validation"]["results"][0]["rms"] = 0.059
        self.assertEqual(validate_instance(impossible_rms_ceiling, self.schema), [])
        rms_ceiling_codes = {item["code"] for item in validate_contract(impossible_rms_ceiling)["errors"]}
        self.assertIn("validation.certificate_rms", rms_ceiling_codes)

        impossible_mean_ceiling = copy.deepcopy(self.valid)
        result = impossible_mean_ceiling["validation"]["results"][0]
        result.update({"mean": 0.05, "rms": 0.055})
        mean_ceiling_codes = {item["code"] for item in validate_contract(impossible_mean_ceiling)["errors"]}
        self.assertIn("validation.certificate_mean", mean_ceiling_codes)

        impossible_mean_floor = copy.deepcopy(self.valid)
        result = impossible_mean_floor["validation"]["results"][0]
        result.update({"mean": 0.02, "rms": 0.04})
        mean_floor_codes = {item["code"] for item in validate_contract(impossible_mean_floor)["errors"]}
        self.assertIn("validation.certificate_mean", mean_floor_codes)

        for rms in (0.044, 0.0508):
            with self.subTest(certificate_rms=rms):
                mutation = copy.deepcopy(self.valid)
                mutation["validation"]["results"][0]["rms"] = rms
                self.assertIn(
                    "validation.certificate_rms",
                    {item["code"] for item in validate_contract(mutation)["errors"]},
                )

        for mean in (0.047, 0.028):
            with self.subTest(certificate_mean=mean):
                mutation = copy.deepcopy(self.valid)
                mutation["validation"]["results"][0]["mean"] = mean
                self.assertIn(
                    "validation.certificate_mean",
                    {item["code"] for item in validate_contract(mutation)["errors"]},
                )

        coupled = copy.deepcopy(self.valid)
        coupled_result = coupled["validation"]["results"][0]
        coupled_result["percentiles"][0]["distance"] = 0.05
        coupled_result.update({"mean": 0.03875, "rms": 0.05})
        coupled_codes = {item["code"] for item in validate_contract(coupled)["errors"]}
        self.assertTrue(
            {"validation.certificate_percentile", "validation.certificate_mean", "validation.certificate_rms"}
            & coupled_codes
        )

        impossible_upper = copy.deepcopy(self.valid)
        result = impossible_upper["validation"]["results"][0]
        result.update(
            {
                "within_tolerance_percent": 87.5,
                "mean": 0.3,
                "rms": 0.3,
                "maximum": 0.3,
                "percentiles": [
                    {"percentile": 50, "distance": 0.2},
                    {"percentile": 95, "distance": 0.265},
                    {"percentile": 98, "distance": 0.286},
                    {"percentile": 99, "distance": 0.293},
                ],
            }
        )
        result["acceptance_criteria"].update(
            {
                "minimum_within_tolerance_percent": 80,
                "maximum_distance": 0.3,
                "percentile_gates": [
                    {"percentile": percentile, "maximum_distance": 0.3}
                    for percentile in (50, 95, 98, 99)
                ],
            }
        )
        upper_report = validate_contract(impossible_upper)
        upper_codes = {item["code"] for item in upper_report["errors"]}
        self.assertIn("validation.certificate_scale", upper_codes)

        impossible_outside = copy.deepcopy(self.valid)
        result = impossible_outside["validation"]["results"][0]
        result.update(
            {
                "within_tolerance_percent": 50,
                "mean": 0.08,
                "rms": 0.08,
                "maximum": 0.21,
                "percentiles": [
                    {"percentile": 50, "distance": 0.10005},
                    {"percentile": 95, "distance": 0.206535},
                    {"percentile": 98, "distance": 0.208614},
                    {"percentile": 99, "distance": 0.209307},
                ],
            }
        )
        result["acceptance_criteria"].update(
            {
                "minimum_within_tolerance_percent": 50,
                "maximum_distance": 0.21,
                "percentile_gates": [
                    {"percentile": percentile, "maximum_distance": 0.21}
                    for percentile in (50, 95, 98, 99)
                ],
            }
        )
        outside_report = validate_contract(impossible_outside)
        outside_codes = {item["code"] for item in outside_report["errors"]}
        self.assertIn("validation.certificate_scale", outside_codes)

    def test_canonical_summaries_are_derived_from_realizable_samples(self) -> None:
        distances_by_id = {
            "cloud-to-step-global": [0, 0.01, 0.02, 0.025, 0.03, 0.04, 0.06, 0.1],
            "step-to-cloud-global": [0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.08, 0.12],
            "cloud-to-step-critical": [0.01, 0.02, 0.04, 0.1],
            "step-to-cloud-critical": [0.01, 0.03, 0.05, 0.12],
        }
        for result in self.valid["validation"]["results"]:
            if result["id"] not in distances_by_id:
                continue
            distances = distances_by_id[result["id"]]
            self.assertAlmostEqual(result["mean"], sum(distances) / len(distances))
            self.assertAlmostEqual(result["rms"], math.sqrt(sum(value * value for value in distances) / len(distances)))
            for percentile_result in result["percentiles"]:
                position = (len(distances) - 1) * percentile_result["percentile"] / 100
                lower = math.floor(position)
                upper = math.ceil(position)
                fraction = position - lower
                expected = distances[lower] * (1 - fraction) + distances[upper] * fraction
                self.assertAlmostEqual(percentile_result["distance"], expected)

    def test_realizability_certificate_is_the_summary_truth_source(self) -> None:
        missing = copy.deepcopy(self.valid)
        del missing["validation"]["results"][0]["realizability_certificate"]
        self.assertIn("schema.required", {item["code"] for item in validate_contract(missing)["errors"]})

        malformed = copy.deepcopy(self.valid)
        block = malformed["validation"]["results"][0]["realizability_certificate"]["blocks"][0]
        block.update({"start_index": 2, "end_index": 1})
        self.assertEqual(validate_instance(malformed, self.schema), [])
        malformed_report = validate_contract(malformed)
        self.assertIn("validation.certificate_partition", {item["code"] for item in malformed_report["errors"]})
        with tempfile.TemporaryDirectory() as directory:
            contract_path = Path(directory) / "malformed-certificate.json"
            contract_path.write_text(json.dumps(malformed), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_feature_contract.py"), str(contract_path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(completed.stderr, "")
            self.assertIn("validation.certificate_partition", {item["code"] for item in json.loads(completed.stdout)["errors"]})

        impossible_interior = copy.deepcopy(self.valid)
        impossible_interior["validation"]["results"][0]["realizability_certificate"]["blocks"][0]["sum_squares"] = 0.049
        interior_report = validate_contract(impossible_interior)
        self.assertIn("validation.certificate_moments", {item["code"] for item in interior_report["errors"]})

        endpoint_underflow = copy.deepcopy(self.valid)
        endpoint = endpoint_underflow["validation"]["results"][2]["realizability_certificate"]["blocks"][0]
        endpoint.update({"first": 5e-324, "last": 5e-324, "sum": 5e-324, "sum_squares": 0})
        underflow_report = validate_contract(endpoint_underflow)
        self.assertIn("validation.certificate_precision", {item["code"] for item in underflow_report["errors"]})

        for field, invalid_value, expected_code in (
            ("sum", 1e308, "validation.certificate_precision"),
            ("sum_squares", 1e308, "validation.certificate_precision"),
            ("sum", -10, "structure.minimum"),
            ("sum_squares", -10, "structure.minimum"),
        ):
            overflow = copy.deepcopy(self.valid)
            overflow["validation"]["results"][0]["realizability_certificate"]["blocks"][0][field] = invalid_value
            overflow_report = validate_contract(overflow, schema=True)
            self.assertFalse(overflow_report["contract_valid"])
            self.assertIn(
                expected_code,
                {item["code"] for item in overflow_report["errors"]},
            )

        malformed_mixture = copy.deepcopy(self.valid)
        malformed_blocks = malformed_mixture["validation"]["results"][0]["realizability_certificate"]["blocks"]
        malformed_blocks[2]["sum_squares"] = -10
        malformed_blocks[5]["threshold_class"] = {}
        malformed_report = validate_contract(malformed_mixture, schema=True)
        self.assertFalse(malformed_report["contract_valid"])
        self.assertTrue(
            {"structure.minimum", "validation.certificate_threshold"}.issubset(
                {item["code"] for item in malformed_report["errors"]}
            )
        )

        exact_threshold = copy.deepcopy(self.valid)
        result = exact_threshold["validation"]["results"][0]
        self._set_distance_evidence(
            result,
            [0, 0, 0.01, 0.02, 0.03, 0.04, 0.2, math.nextafter(0.2, math.inf)],
        )
        result["acceptance_criteria"].update(
            {
                "minimum_within_tolerance_percent": 80,
                "maximum_distance": 1,
                "percentile_gates": [
                    {"percentile": percentile, "maximum_distance": 1}
                    for percentile in (50, 95, 98, 99)
                ],
            }
        )
        self._assert_valid_diagnostic(exact_threshold, "pass")
        blocks = result["realizability_certificate"]["blocks"]
        self.assertEqual(sum(block["end_index"] - block["start_index"] + 1 for block in blocks if block["threshold_class"] == "within"), 7)

    def test_semantic_only_minimum_violations_fail_closed(self) -> None:
        for field in ("mean", "maximum", "evaluated_count"):
            with self.subTest(field=field):
                contract = copy.deepcopy(self.valid)
                contract["validation"]["results"][0][field] = -1
                report = validate_contract(contract, schema=True)
                self.assertFalse(report["contract_valid"])
                self.assertIn("structure.minimum", {item["code"] for item in report["errors"]})

        exclusive = copy.deepcopy(self.valid)
        exclusive["validation"]["results"][0]["tolerance"] = 0
        exclusive_report = validate_contract(exclusive, schema=True)
        self.assertFalse(exclusive_report["contract_valid"])
        self.assertIn("structure.minimum", {item["code"] for item in exclusive_report["errors"]})

        malformed_bounds = copy.deepcopy(self.valid)
        malformed_bounds["samples"]["display"]["bounds"]["min"][2] = None
        bounds_report = validate_contract(malformed_bounds, schema=True)
        self.assertFalse(bounds_report["contract_valid"])
        self.assertIn("structure.number", {item["code"] for item in bounds_report["errors"]})

        with mock.patch.object(contract_tools, "_check_samples", side_effect=TypeError("private malformed leaf")):
            guarded_report = validate_contract(copy.deepcopy(self.valid), schema=True)
        self.assertFalse(guarded_report["contract_valid"])
        self.assertEqual(guarded_report["errors"][0]["code"], "validation.malformed_semantics")
        self.assertNotIn("private malformed leaf", json.dumps(guarded_report))

    def test_certificate_quantile_indices_use_exact_integer_arithmetic(self) -> None:
        count = 2**53 - 1
        for percentile in (50, 95, 98, 99):
            lower, upper, fraction = contract_tools._fixed_percentile_position(count, percentile)
            exact_lower, remainder = divmod((count - 1) * percentile, 100)
            self.assertEqual(lower, exact_lower)
            self.assertEqual(upper, exact_lower + bool(remainder))
            self.assertEqual(fraction, remainder / 100)

    def test_certificate_count_is_not_reconstructed_from_rounded_percentage(self) -> None:
        count = 9_007_199_254_740_989
        within_count = 4_503_599_627_370_495
        contract = copy.deepcopy(self.valid)
        contract["source"]["point_count"] = count
        contract["samples"]["measurement"]["source_point_count"] = count
        contract["samples"]["measurement"]["point_count"] = count
        contract["samples"]["display"]["source_point_count"] = count

        result = contract["validation"]["results"][0]
        result.update(
            {
                "eligible_count": count,
                "evaluated_count": count,
                "tolerance": 0.5,
                "within_tolerance_percent": 100.0 * within_count / count,
                "mean": (count - within_count) / count,
                "rms": math.sqrt((count - within_count) / count),
                "percentiles": [
                    {"percentile": 50, "distance": 0},
                    {"percentile": 95, "distance": 1},
                    {"percentile": 98, "distance": 1},
                    {"percentile": 99, "distance": 1},
                ],
                "maximum": 1,
            }
        )
        result["acceptance_criteria"].update(
            {
                "minimum_within_tolerance_percent": 1,
                "maximum_distance": 1,
                "percentile_gates": [
                    {"percentile": percentile, "maximum_distance": 1}
                    for percentile in (50, 95, 98, 99)
                ],
            }
        )
        boundaries = {0, count, within_count}
        for percentile in (50, 95, 98, 99):
            lower, upper, _ = contract_tools._fixed_percentile_position(count, percentile)
            boundaries.update((lower, lower + 1, upper, upper + 1))
        ordered_boundaries = sorted(boundary for boundary in boundaries if 0 <= boundary <= count)
        blocks = []
        for start, stop in zip(ordered_boundaries, ordered_boundaries[1:]):
            if start == stop:
                continue
            value = 0 if stop <= within_count else 1
            block_count = stop - start
            blocks.append(
                {
                    "start_index": start,
                    "end_index": stop - 1,
                    "first": value,
                    "last": value,
                    "sum": block_count * value,
                    "sum_squares": block_count * value,
                    "threshold_class": "within" if value == 0 else "outside",
                }
            )
        result["realizability_certificate"] = {
            "version": "normalized-blocks-v1",
            "scale": 1,
            "blocks": blocks,
        }
        self.assertEqual(result["within_tolerance_percent"], 50.0)
        self.assertEqual(validate_instance(contract, self.schema), [])
        self._assert_valid_diagnostic(contract, "pass")

    def test_certificate_percentage_allows_binary64_operation_order_but_gate_uses_exact_count(self) -> None:
        contract = copy.deepcopy(self.valid)
        measurement = contract["samples"]["measurement"]
        measurement["point_count"] = 3
        measurement["method"] = "hash-rank"
        measurement["parameters"] = {"target_count": 3}
        self._set_distance_evidence(
            contract["validation"]["results"][2],
            [0.01, 0.02, 0.03],
        )

        result = contract["validation"]["results"][0]
        displayed_percentage = (1.0 / 3.0) * 100.0
        certified_percentage = 100.0 * 1 / 3
        self.assertNotEqual(displayed_percentage, certified_percentage)
        result.update(
            {
                "eligible_count": 3,
                "evaluated_count": 3,
                "tolerance": 0.5,
                "within_tolerance_percent": displayed_percentage,
                "mean": 2.0 / 3.0,
                "rms": math.sqrt(2.0 / 3.0),
                "percentiles": [
                    {"percentile": percentile, "distance": 1}
                    for percentile in (50, 95, 98, 99)
                ],
                "maximum": 1,
                "realizability_certificate": {
                    "version": "normalized-blocks-v1",
                    "scale": 1,
                    "blocks": [
                        {
                            "start_index": 0,
                            "end_index": 0,
                            "first": 0,
                            "last": 0,
                            "sum": 0,
                            "sum_squares": 0,
                            "threshold_class": "within",
                        },
                        {
                            "start_index": 1,
                            "end_index": 2,
                            "first": 1,
                            "last": 1,
                            "sum": 2,
                            "sum_squares": 2,
                            "threshold_class": "outside",
                        },
                    ],
                },
            }
        )
        result["acceptance_criteria"].update(
            {
                "minimum_within_tolerance_percent": certified_percentage,
                "maximum_distance": 1,
                "percentile_gates": [
                    {"percentile": percentile, "maximum_distance": 1}
                    for percentile in (50, 95, 98, 99)
                ],
            }
        )
        self.assertEqual(validate_instance(contract, self.schema), [])
        self._assert_valid_diagnostic(contract, "pass")

    def test_informational_normals_require_a_valid_non_gating_certificate(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["source"]["point_record"] = "xyz-normals"
        result = contract["validation"]["results"][0]
        self._set_required_normal_evidence(result, [0, 0, 0, 1, 1, 1, 2, 3], threshold=2)
        result["normal_agreement"]["applicability"] = "informational"
        self._assert_valid_diagnostic(contract, "pass")

        missing = copy.deepcopy(contract)
        del missing["validation"]["results"][0]["normal_agreement"]["realizability_certificate"]
        self.assertIn("schema.required", {item["code"] for item in validate_contract(missing)["errors"]})

        impossible = copy.deepcopy(contract)
        impossible["validation"]["results"][0]["normal_agreement"]["realizability_certificate"]["blocks"][0]["sum_squares"] = 1
        self.assertIn(
            "validation.certificate_moments",
            {item["code"] for item in validate_contract(impossible)["errors"]},
        )

    def test_same_order_statistic_bin_percentiles_must_be_affine(self) -> None:
        contract = copy.deepcopy(self.valid)
        result = contract["validation"]["results"][0]
        result["percentiles"][-1]["distance"] += 0.001
        report = validate_contract(contract)
        self.assertIn("validation.percentile_interpolation", {item["code"] for item in report["errors"]})

        wrong_final_endpoint = copy.deepcopy(self.valid)
        wrong_final_endpoint["validation"]["results"][0]["percentiles"] = [
            {"percentile": 50, "distance": 0.03},
            {"percentile": 95, "distance": 0.073},
            {"percentile": 98, "distance": 0.0772},
            {"percentile": 99, "distance": 0.0786},
        ]
        endpoint_report = validate_contract(wrong_final_endpoint)
        self.assertIn("validation.percentile_interpolation", {item["code"] for item in endpoint_report["errors"]})

        single_final_bin = copy.deepcopy(self.valid)
        single_final_bin["source"]["point_count"] = 100
        single_final_bin["samples"]["measurement"]["source_point_count"] = 100
        single_final_bin["samples"]["measurement"]["point_count"] = 100
        single_final_bin["samples"]["display"]["source_point_count"] = 100
        single_final_bin["authority"]["validation_sample"]["point_count"] = 100
        for global_result in single_final_bin["validation"]["results"][:2]:
            global_result["eligible_count"] = 100
            global_result["evaluated_count"] = 100
        result = single_final_bin["validation"]["results"][0]
        result.update(
            {
                "tolerance": 200,
                "within_tolerance_percent": 100,
                "mean": 1,
                "rms": 10,
                "maximum": 100,
                "percentiles": [
                    {"percentile": 50, "distance": 0},
                    {"percentile": 95, "distance": 0.1},
                    {"percentile": 98, "distance": 0.2},
                    {"percentile": 99, "distance": 0.5},
                ],
            }
        )
        result["acceptance_criteria"].update(
            {
                "maximum_distance": 100,
                "percentile_gates": [
                    {"percentile": percentile, "maximum_distance": 100}
                    for percentile in (50, 95, 98, 99)
                ],
            }
        )
        single_report = validate_contract(single_final_bin)
        self.assertIn("validation.percentile_interpolation", {item["code"] for item in single_report["errors"]})

        one_point = copy.deepcopy(self.valid)
        result = one_point["validation"]["results"][2]
        result.update(
            {
                "eligible_count": 1,
                "evaluated_count": 1,
                "tolerance": 1,
                "within_tolerance_percent": 100,
                "mean": 0.5,
                "rms": 0.5,
                "maximum": 0.5,
                "percentiles": [
                    {"percentile": 50, "distance": 0.1},
                    {"percentile": 95, "distance": 0.2},
                    {"percentile": 98, "distance": 0.3},
                    {"percentile": 99, "distance": 0.4},
                ],
            }
        )
        result["acceptance_criteria"].update(
            {
                "minimum_within_tolerance_percent": 1,
                "maximum_distance": 1,
                "percentile_gates": [
                    {"percentile": percentile, "maximum_distance": 1}
                    for percentile in (50, 95, 98, 99)
                ],
            }
        )
        self.assertEqual(validate_instance(one_point, self.schema), [])
        one_point_report = validate_contract(one_point)
        self.assertIn("validation.percentile_interpolation", {item["code"] for item in one_point_report["errors"]})

        shared_endpoint = copy.deepcopy(self.valid)
        shared_endpoint["validation"]["results"][2]["percentiles"][0]["distance"] = 0.08
        shared_report = validate_contract(shared_endpoint)
        self.assertIn("validation.percentile_interpolation", {item["code"] for item in shared_report["errors"]})

    def test_semantic_diagnostics_have_a_hard_bounded_output_budget(self) -> None:
        contract = copy.deepcopy(self.valid)
        result = contract["validation"]["results"][0]
        result["percentiles"] = [{"percentile": 99, "distance": 0.0972} for _ in range(1000)]
        result["acceptance_criteria"]["percentile_gates"] = [
            {"percentile": 99, "maximum_distance": 0} for _ in range(1000)
        ]
        self.assertTrue(validate_instance(contract, self.schema))
        report = validate_contract(contract)
        self.assertFalse(report["contract_valid"])
        self.assertLessEqual(report["error_count"] + report["warning_count"], contract_tools.MAX_SEMANTIC_DIAGNOSTICS)
        self.assertIn("schema.max_items", {item["code"] for item in report["errors"]})
        self.assertEqual(report["evidence_results"], [])
        self.assertLess(len(json.dumps(report)), 100_000)

    def test_finite_count_and_percentile_moment_bounds_are_enforced(self) -> None:
        def set_summary(contract: dict, mean: float, rms: float, p50: float) -> dict:
            result = contract["validation"]["results"][0]
            result.update(
                {
                    "tolerance": 2,
                    "within_tolerance_percent": 100,
                    "mean": mean,
                    "rms": rms,
                    "maximum": 1,
                    "percentiles": [
                        {"percentile": 50, "distance": p50},
                        {"percentile": 95, "distance": 0.93},
                        {"percentile": 98, "distance": 0.972},
                        {"percentile": 99, "distance": 0.986},
                    ],
                }
            )
            result["acceptance_criteria"].update(
                {
                    "minimum_within_tolerance_percent": 1,
                    "maximum_distance": 2,
                    "percentile_gates": [
                        {"percentile": percentile, "maximum_distance": 2}
                        for percentile in (50, 95, 98, 99)
                    ],
                }
            )
            return result

        lower_bound = copy.deepcopy(self.valid)
        set_summary(lower_bound, 0.5, 0.52, 0.3)
        lower_codes = {item["code"] for item in validate_contract(lower_bound)["errors"]}
        self.assertIn("validation.finite_count_rms_bound", lower_codes)

        percentile_ceiling = copy.deepcopy(self.valid)
        set_summary(percentile_ceiling, 0.9, 0.92, 0.1)
        ceiling_codes = {item["code"] for item in validate_contract(percentile_ceiling)["errors"]}
        self.assertIn("validation.percentile_mean_ceiling", ceiling_codes)
        self.assertIn("validation.percentile_rms_ceiling", ceiling_codes)

        boundary = copy.deepcopy(self.valid)
        repeated = 3 / 7
        result = set_summary(
            boundary,
            0.5,
            math.sqrt((1 + 7 * repeated * repeated) / 8),
            repeated,
        )
        self._set_distance_evidence(result, [repeated] * 7 + [1])
        self._assert_valid_diagnostic(boundary, "pass")

    def test_stdlib_schema_subset_rejects_every_used_unsupported_keyword(self) -> None:
        self.assertEqual(check_supported_schema(self.schema), [])
        unsupported = copy.deepcopy(self.schema)
        unsupported["format"] = "uri"
        issues = check_supported_schema(unsupported)
        self.assertIn("schema.unsupported_keyword", {item.code for item in issues})

    def test_schema_unique_items_uses_json_numeric_equality(self) -> None:
        schema = {"type": "array", "uniqueItems": True, "items": {"type": "number"}}
        issues = validate_instance([95, 95.0], schema)
        self.assertIn("schema.unique_items", {item.code for item in issues})

    def test_structural_mutations_match_full_draft_2020_12_validator(self) -> None:
        mutations = []

        def mutated(change):
            contract = copy.deepcopy(self.valid)
            change(contract)
            return contract

        mutations.extend(
            [
                ("algorithm-version", mutated(lambda c: c["samples"]["display"].__setitem__("algorithm_version", "INVALID VERSION"))),
                ("seed-maximum", mutated(lambda c: c["samples"]["display"].__setitem__("seed", 4294967296))),
                ("empty-tool", mutated(lambda c: c["authority"]["producer"].__setitem__("tool", ""))),
                ("empty-notes", mutated(lambda c: c["authority"]["independent_reopen"].__setitem__("notes", ""))),
                ("media-type", mutated(lambda c: c["source"]["artifact"].__setitem__("media_type", "not a media type"))),
                ("axis-length", mutated(lambda c: c["frames"][0].__setitem__("x_axis", "x" * 121))),
                ("duplicate-critical-id", mutated(lambda c: c["validation"]["requirements"]["critical_component_ids"].append("main-body"))),
            ]
        )
        full_validator = None
        if importlib.util.find_spec("jsonschema") is not None:
            from jsonschema import Draft202012Validator

            full_validator = Draft202012Validator(self.schema)
        for name, contract in mutations:
            with self.subTest(name=name):
                subset_errors = validate_instance(contract, self.schema)
                self.assertTrue(subset_errors)
                if full_validator is not None:
                    self.assertTrue(list(full_validator.iter_errors(contract)))
                report = validate_contract(contract)
                self.assertFalse(report["contract_valid"])
                self.assertTrue(any(item["code"].startswith("schema.") for item in report["errors"]))

    def test_schema_subset_matches_full_validator_for_all_bundled_contracts(self) -> None:
        if importlib.util.find_spec("jsonschema") is None:
            self.skipTest("optional jsonschema package is unavailable")
        from jsonschema import Draft202012Validator

        full = Draft202012Validator(self.schema)
        paths = [ASSETS / "feature-contract.example.json", *sorted((ASSETS / "contracts").glob("*.json"))]
        for path in paths:
            with self.subTest(path=path.name):
                contract = load_json_strict(path)
                self.assertEqual(bool(validate_instance(contract, self.schema)), bool(list(full.iter_errors(contract))))

    def test_sample_and_authority_frames_require_declared_transform_lineage(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["frames"].append(
            {"id": "isolated", "handedness": "right", "x_axis": "x", "y_axis": "y", "z_axis": "z"}
        )
        contract["samples"]["display"]["frame"] = "isolated"
        contract["samples"]["display"]["bounds"]["frame"] = "isolated"
        report = validate_contract(contract)
        self.assertIn("reference.transform_path", {item["code"] for item in report["errors"]})

        authority_contract = copy.deepcopy(self.valid)
        authority_contract["authority"]["validation_sample"]["frame"] = "source"
        authority_contract["authority"]["validation_sample"]["bounds"]["frame"] = "source"
        authority_report = validate_contract(authority_contract)
        self.assertIn("lineage.authority_sample_frame", {item["code"] for item in authority_report["errors"]})

    def test_result_transform_order_mask_frame_and_critical_bidirectionality_are_checked(self) -> None:
        chain = copy.deepcopy(self.valid)
        chain["validation"]["results"][0]["transform_ids"] = []
        self.assertIn("reference.transform_order", {item["code"] for item in validate_contract(chain)["errors"]})

        frame = copy.deepcopy(self.valid)
        frame["masks"][1]["frame"] = "source"
        frame_report = validate_contract(frame)
        self.assertIn("lineage.mask_frame", {item["code"] for item in frame_report["errors"]})

        directions = copy.deepcopy(self.valid)
        directions["validation"]["results"][3]["mask_ids"] = ["global-fit"]
        directions_report = validate_contract(directions)
        self.assertIn("validation.local_results", {item["code"] for item in directions_report["errors"]})

    def test_result_and_normal_counts_are_bounded_by_recorded_query_evidence(self) -> None:
        huge = copy.deepcopy(self.valid)
        huge["validation"]["results"][0]["evaluated_count"] = 10**12
        huge_report = validate_contract(huge)
        self.assertIn("validation.evaluated_count", {item["code"] for item in huge_report["errors"]})

        normals = copy.deepcopy(self.valid)
        normals["source"]["point_record"] = "xyz-normals"
        result = normals["validation"]["results"][0]
        self._set_required_normal_evidence(result, [1])
        self._set_normal_gates(result)
        normals_report = validate_contract(normals)
        self.assertIn("validation.normal_count", {item["code"] for item in normals_report["errors"]})

    def test_within_percentage_is_realizable_by_evaluated_count(self) -> None:
        contract = copy.deepcopy(self.valid)
        result = contract["validation"]["results"][0]
        result["within_tolerance_percent"] = 99
        report = validate_contract(contract)
        self.assertIn("validation.certificate_threshold_count", {item["code"] for item in report["errors"]})

    def test_exclusion_mask_component_and_frame_follow_semantic_target(self) -> None:
        contract = copy.deepcopy(self.valid)
        exclusion_mask = next(mask for mask in contract["masks"] if mask["id"] == "fixture-region")
        exclusion_mask["component_id"] = "other-body"
        for result in contract["validation"]["results"]:
            result["exclusion_ids"] = ["exclude-fixture"]
        report = validate_contract(contract)
        self.assertIn("lineage.exclusion_component", {item["code"] for item in report["errors"]})

    def test_excluded_results_cannot_satisfy_critical_feature_evidence(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["exclusions"].append(
            {
                "id": "exclude-critical", "mask_id": "critical-body", "reason": "documented-outlier",
                "rationale": "adversarial attempt to exclude required evidence", "approved": True,
            }
        )
        for result in contract["validation"]["results"]:
            result["exclusion_ids"] = ["exclude-critical"]
        report = validate_contract(contract)
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("validation.exclusion_overlap", codes)
        self.assertIn("validation.local_results", codes)

        numeric_overlap = copy.deepcopy(self.valid)
        critical_mask = next(mask for mask in numeric_overlap["masks"] if mask["id"] == "critical-body")
        exclusion_mask = next(mask for mask in numeric_overlap["masks"] if mask["id"] == "fixture-region")
        exclusion_mask["definition"] = copy.deepcopy(critical_mask["definition"])
        exclusion_mask["definition"]["min"][0] = 10.0
        exclusion_mask["definition_sha256"] = canonical_json_sha256(exclusion_mask["definition"])
        numeric_overlap["validation"]["results"][2]["exclusion_ids"] = ["exclude-fixture"]
        numeric_codes = {item["code"] for item in validate_contract(numeric_overlap)["errors"]}
        self.assertIn("validation.exclusion_overlap", numeric_codes)

    def test_unperformed_section_and_trim_evidence_is_inconclusive(self) -> None:
        contract = copy.deepcopy(self.valid)
        for result in contract["validation"]["results"]:
            result["section_trim_evidence"] = {
                "defining_section_ids": [], "trim_boundary_ids": [], "passed": False,
                "not_applicable_reason": "not applicable",
            }
            result["acceptance_status"] = "inconclusive"
        report = self._assert_valid_diagnostic(contract, "inconclusive")
        self.assertTrue(any("trim-boundary validation was not performed" in reason for reason in report["evidence_results"][0]["reasons"]))

    def test_sampling_counts_follow_declared_deterministic_algorithm(self) -> None:
        under_sampled = copy.deepcopy(self.valid)
        under_sampled["samples"]["display"]["point_count"] = 1
        report = validate_contract(under_sampled)
        self.assertIn("sampling.algorithm_count", {item["code"] for item in report["errors"]})

        masked = copy.deepcopy(self.valid)
        sample = masked["samples"]["display"]
        sample["method"] = "masked-hash-rank"
        sample["parameters"] = {"target_count": 4, "eligible_count": 9, "mask_sha256": "f" * 64}
        masked_report = validate_contract(masked)
        self.assertIn("sampling.eligible_count", {item["code"] for item in masked_report["errors"]})

    def test_full_sample_must_preserve_source_order_hash(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["samples"]["measurement"]["canonical_points_sha256"] = "b" * 64
        report = validate_contract(contract)
        self.assertIn("sampling.full_order", {item["code"] for item in report["errors"]})

    def test_transform_inverse_reflection_roundtrip_and_graph_cycles_are_checked(self) -> None:
        inverse = copy.deepcopy(self.valid)
        inverse["transforms"][0]["inverse_matrix"][3] = -11
        self.assertIn("transform.inverse", {item["code"] for item in validate_contract(inverse)["errors"]})

        reflection = copy.deepcopy(self.valid)
        reflection["transforms"][0]["matrix"][0] = -1
        reflection["transforms"][0]["inverse_matrix"][0] = -1
        reflection["transforms"][0]["inverse_matrix"][3] = 10
        reflection_codes = {item["code"] for item in validate_contract(reflection)["errors"]}
        self.assertIn("transform.undocumented_reflection", reflection_codes)

        roundtrip = copy.deepcopy(self.valid)
        roundtrip["transforms"][0]["round_trip_max"] = 0.01
        self.assertIn("transform.round_trip", {item["code"] for item in validate_contract(roundtrip)["errors"]})

        projective = copy.deepcopy(self.valid)
        projective["transforms"][0]["matrix"] = [
            1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1e-11, 0, 0, 1,
        ]
        projective["transforms"][0]["inverse_matrix"] = [
            1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -1e-11, 0, 0, 1,
        ]
        self.assertIn("transform.homogeneous_row", {item["code"] for item in validate_contract(projective)["errors"]})

        shear = copy.deepcopy(self.valid)
        epsilon = 1e-8
        transform = shear["transforms"][0]
        transform["matrix"] = [
            1, epsilon, 0, 10, 0, 1, 0, 20, 0, 0, 1, 30, 0, 0, 0, 1,
        ]
        transform["inverse_matrix"] = [
            1, -epsilon, 0, -10 + 20 * epsilon,
            0, 1, 0, -20,
            0, 0, 1, -30,
            0, 0, 0, 1,
        ]
        condition_number = (1 + epsilon) ** 2
        transform["conditioning"]["condition_number"] = condition_number
        transform["conditioning"]["reciprocal_condition"] = 1 / condition_number
        shear["source"]["bounds"]["max"][1] = 1e12
        shear["samples"]["measurement"]["bounds"]["max"][1] = 1e12
        shear_codes = {item["code"] for item in validate_contract(shear)["errors"]}
        self.assertIn("transform.non_orthogonal", shear_codes)

        cycle = copy.deepcopy(self.valid)
        cycle["frames"].append({"id": "aux", "handedness": "right", "x_axis": "x", "y_axis": "y", "z_axis": "z"})
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        for transform_id, source, target in (("source-to-aux", "source", "aux"), ("aux-to-cad", "aux", "cad")):
            cycle["transforms"].append(
                {
                    "id": transform_id, "from_frame": source, "to_frame": target,
                    "layout": "row-major", "vector_convention": "column-vector",
                    "translation_units": "contract-linear-units", "transform_type": "rigid",
                    "matrix": identity, "inverse_matrix": identity, "reflection_allowed": False,
                    "held_out_count": 8, "round_trip_max": 0, "round_trip_tolerance": 1e-9,
                    "conditioning": {"norm": "infinity", "condition_number": 1, "reciprocal_condition": 1, "evidence": "identity canary"},
                }
            )
        self.assertIn("transform.cycle", {item["code"] for item in validate_contract(cycle)["errors"]})

    def test_normals_and_signed_bias_semantics_are_explicit(self) -> None:
        rgb = copy.deepcopy(self.valid)
        rgb["source"]["point_record"] = "xyz-rgb"
        self._set_required_normal_evidence(rgb["validation"]["results"][0], [0, 0, 0, 1, 1, 1, 2, 3])
        rgb["validation"]["results"][0]["normal_agreement"]["quality_evidence"] = "scanner export"
        self._set_normal_gates(rgb["validation"]["results"][0])
        self.assertIn("validation.normal_source", {item["code"] for item in validate_contract(rgb)["errors"]})

        normals = copy.deepcopy(self.valid)
        normals["source"]["point_record"] = "xyz-normals-rgb"
        for result in normals["validation"]["results"]:
            count = result["evaluated_count"]
            self._set_required_normal_evidence(result, ([0] * (count - 3)) + [1, 2, 3])
            result["normal_agreement"]["quality_evidence"] = "unit-length normal audit"
            self._set_normal_gates(result)
        self._assert_valid_diagnostic(normals, "pass")

        signed = copy.deepcopy(self.valid)
        signed["validation"]["results"][0]["signedness"] = "signed"
        signed["validation"]["results"][0]["signed_bias"] = -0.01
        signed_report = validate_contract(signed)
        self.assertFalse(signed_report["contract_valid"])
        self.assertTrue({"schema.const", "schema.additional_property"} & {item["code"] for item in signed_report["errors"]})

    def test_required_normal_gates_and_signed_magnitude_consistency_prevent_false_green(self) -> None:
        normals = copy.deepcopy(self.valid)
        normals["source"]["point_record"] = "xyz-normals"
        for index, result in enumerate(normals["validation"]["results"]):
            angle = 180 if index == 0 else 3
            self._set_required_normal_evidence(result, [angle] * result["evaluated_count"])
            self._set_normal_gates(result)
        normals["validation"]["results"][0]["acceptance_status"] = "fail"
        normals_report = self._assert_valid_diagnostic(normals, "fail")
        self.assertIn("normal maximum angle above gate", normals_report["evidence_results"][0]["reasons"])

        impossible_mean = copy.deepcopy(self.valid)
        impossible_mean["source"]["point_record"] = "xyz-normals"
        for result in impossible_mean["validation"]["results"]:
            count = result["evaluated_count"]
            self._set_required_normal_evidence(result, ([0] * (count - 3)) + [1, 2, 3])
            self._set_normal_gates(result)
        impossible_mean["validation"]["results"][0]["normal_agreement"]["mean_angle_deg"] = 0
        impossible_report = validate_contract(impossible_mean)
        self.assertIn("validation.certificate_mean", {item["code"] for item in impossible_report["errors"]})

        impossible_endpoint = copy.deepcopy(normals)
        critical_normal = impossible_endpoint["validation"]["results"][2]["normal_agreement"]
        critical_normal.update({"mean_angle_deg": 1, "p95_angle_deg": 2, "maximum_angle_deg": 3})
        endpoint_codes = {item["code"] for item in validate_contract(impossible_endpoint)["errors"]}
        self.assertTrue({"validation.normal_percentile_interpolation", "validation.certificate_percentile"} & endpoint_codes)

        for mean_angle, expected_code in (
            (1.5, "validation.normal_mean_ceiling"),
            (0.3, "validation.normal_mean_floor"),
        ):
            with self.subTest(mean_angle=mean_angle):
                bounded_normal = copy.deepcopy(self.valid)
                bounded_normal["source"]["point_record"] = "xyz-normals"
                result = bounded_normal["validation"]["results"][0]
                inferred = (1.7 - 0.65 * 2) / 0.35
                self._set_required_normal_evidence(result, [0, 0, 0, 0, 0, 0, inferred, 2], threshold=5)
                result["normal_agreement"]["mean_angle_deg"] = mean_angle
                self._set_normal_gates(result, mean=5, p95=5, maximum=5)
                codes = {item["code"] for item in validate_contract(bounded_normal)["errors"]}
                self.assertIn("validation.certificate_mean", codes)

        signed = copy.deepcopy(self.valid)
        signed_result = signed["validation"]["results"][0]
        signed_result["signedness"] = "signed"
        signed_result["signed_bias"] = 1
        signed_report = validate_contract(signed)
        self.assertTrue({"schema.const", "schema.additional_property"} & {item["code"] for item in signed_report["errors"]})

    def test_p100_distance_equals_recorded_maximum(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["validation"]["requirements"]["required_percentiles"].append(100)
        for result in contract["validation"]["results"]:
            result["percentiles"].append({"percentile": 100, "distance": result["maximum"]})
            result["acceptance_criteria"]["percentile_gates"].append(
                {"percentile": 100, "maximum_distance": result["acceptance_criteria"]["maximum_distance"]}
            )
        contract["validation"]["results"][0]["percentiles"][-1]["distance"] -= 0.005
        report = validate_contract(contract)
        self.assertIn("schema.max_items", {item["code"] for item in report["errors"]})

    def test_kernel_family_alias_cannot_overclaim_cross_kernel_reopen(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["authority"]["producer"]["kernel"] = "OpenCascade 7.8"
        contract["authority"]["independent_reopen"]["kernel"] = "OCCT 7.8"
        contract["authority"]["independent_reopen"]["validation_tier"] = "cross-kernel"
        report = validate_contract(contract)
        self.assertIn("authority.kernel_lineage", {item["code"] for item in report["errors"]})

        unknown = copy.deepcopy(self.valid)
        unknown["authority"]["producer"]["kernel"] = "unknown-a"
        unknown["authority"]["independent_reopen"]["kernel"] = "unknown-b"
        unknown["authority"]["independent_reopen"]["validation_tier"] = "cross-kernel"
        self.assertIn("authority.kernel_identity", {item["code"] for item in validate_contract(unknown)["errors"]})

        importer = copy.deepcopy(self.valid)
        importer["authority"]["producer"]["tool"] = "FreeCAD"
        importer["authority"]["independent_reopen"]["tool"] = "Free CAD"
        self.assertIn("authority.importer_lineage", {item["code"] for item in validate_contract(importer)["errors"]})

    def test_backend_names_cannot_relabel_point_canaries_as_surface_metrics(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["validation"]["results"][0]["backend"] = "stdlib-bounded"
        report = validate_contract(contract)
        self.assertIn("validation.backend_metric", {item["code"] for item in report["errors"]})

    def test_reverse_direction_is_point_evidence_against_the_measurement_artifact(self) -> None:
        reverse_results = [
            result for result in self.valid["validation"]["results"]
            if result["direction"] == "authority-to-cloud"
        ]
        self.assertTrue(reverse_results)
        for result in reverse_results:
            self.assertEqual(result["metric_kind"], "point-to-point")
            self.assertEqual(result["backend"], "stdlib-bounded")
            self.assertEqual(result["coverage_basis"], "query-points")

        overclaim = copy.deepcopy(self.valid)
        reverse = overclaim["validation"]["results"][1]
        reverse["metric_kind"] = "point-to-surface"
        reverse["backend"] = "cad-kernel"
        reverse["coverage_basis"] = "surface-area"
        overclaim_codes = {item["code"] for item in validate_contract(overclaim)["errors"]}
        self.assertTrue(
            {"validation.reverse_metric", "validation.reverse_backend", "validation.reverse_coverage"}
            .issubset(overclaim_codes)
        )

        wrong_target = copy.deepcopy(self.valid)
        wrong_target["validation"]["results"][1]["target_artifact_sha256"] = wrong_target["authority"]["artifact"]["sha256"]
        self.assertIn("lineage.distance_direction", {item["code"] for item in validate_contract(wrong_target)["errors"]})

    def test_metric_kind_and_coverage_basis_are_compatible(self) -> None:
        for wrong_basis in ("surface-area", "trim-length"):
            with self.subTest(wrong_basis=wrong_basis):
                contract = copy.deepcopy(self.valid)
                contract["validation"]["results"][0]["coverage_basis"] = wrong_basis
                codes = {item["code"] for item in validate_contract(contract)["errors"]}
                self.assertIn("validation.metric_coverage", codes)

        valid_trim = copy.deepcopy(self.valid)
        result = valid_trim["validation"]["results"][0]
        result["metric_kind"] = "trim-boundary-distance"
        result["semantic_target"]["surface_role"] = "trim-boundary"
        result["coverage_basis"] = "trim-length"
        result["section_trim_evidence"] = {
            "defining_section_ids": [],
            "trim_boundary_ids": ["outer-trim"],
            "evidence_sha256": "e" * 64,
            "passed": True,
        }
        trim_report = validate_contract(valid_trim)
        self.assertNotIn("validation.metric_coverage", {item["code"] for item in trim_report["errors"]})

    def test_semantic_metric_kinds_match_target_surface_meaning(self) -> None:
        mutations = (
            ("analytic-surface-residual", {"surface_class": "mesh"}),
            ("section-profile-distance", {"surface_role": "fit-surface"}),
            ("trim-boundary-distance", {"surface_role": "fit-surface"}),
        )
        for metric_kind, target_changes in mutations:
            with self.subTest(metric_kind=metric_kind):
                contract = copy.deepcopy(self.valid)
                for result in contract["validation"]["results"]:
                    result["metric_kind"] = metric_kind
                    result["semantic_target"].update(target_changes)
                report = validate_contract(contract)
                self.assertIn("validation.semantic_metric", {item["code"] for item in report["errors"]})

    def test_uncertainty_completeness_and_reported_only_models_cannot_release_pass(self) -> None:
        incomplete = copy.deepcopy(self.valid)
        incomplete["uncertainty"]["components"] = [
            item for item in incomplete["uncertainty"]["components"] if item["kind"] != "scale"
        ]
        self._set_all_claims(incomplete, "inconclusive")
        incomplete_report = self._assert_valid_diagnostic(incomplete, "inconclusive")
        self.assertIn("uncertainty budget omits required terms", incomplete_report["evidence_results"][0]["reasons"][0])

        no_sampling = copy.deepcopy(self.valid)
        no_sampling["uncertainty"]["components"] = [
            item for item in no_sampling["uncertainty"]["components"] if item["kind"] != "sampling"
        ]
        self._set_all_claims(no_sampling, "inconclusive")
        sampling_report = self._assert_valid_diagnostic(no_sampling, "inconclusive")
        self.assertIn("sampling", sampling_report["evidence_results"][0]["reasons"][0])

        reported = copy.deepcopy(self.valid)
        reported["uncertainty"]["model"] = "reported-only"
        reported["uncertainty"]["combined_standard_uncertainty"] = 0
        reported["uncertainty"]["expanded_uncertainty"] = 0
        self._set_all_claims(reported, "inconclusive")
        reported_report = self._assert_valid_diagnostic(reported, "inconclusive")
        self.assertIn("reported-only uncertainty", reported_report["evidence_results"][0]["reasons"][0])

        underflow = copy.deepcopy(self.valid)
        for component in underflow["uncertainty"]["components"]:
            component["standard_uncertainty"] = 1e-200
        underflow["uncertainty"]["combined_standard_uncertainty"] = 0
        underflow["uncertainty"]["expanded_uncertainty"] = 0
        underflow_report = validate_contract(underflow)
        self.assertIn("uncertainty.combination", {item["code"] for item in underflow_report["errors"]})

    def test_point_artifacts_require_point_evidence_formats(self) -> None:
        mutations = (
            ("source", lambda c: c["source"]["artifact"].__setitem__("format", "png"), "source.format"),
            ("sample", lambda c: c["samples"]["measurement"]["artifact"].__setitem__("format", "step"), "sampling.format"),
            ("authority-sample", lambda c: c["authority"]["validation_sample"]["artifact"].__setitem__("format", "png"), "authority.sample_format"),
        )
        for name, mutate, expected in mutations:
            with self.subTest(name=name):
                contract = copy.deepcopy(self.valid)
                mutate(contract)
                self.assertIn(expected, {item["code"] for item in validate_contract(contract)["errors"]})

    def test_sample_bounds_parameter_masks_and_critical_results_preserve_local_lineage(self) -> None:
        bounds = copy.deepcopy(self.valid)
        bounds["samples"]["measurement"]["bounds"]["max"][0] -= 0.5
        self.assertIn("sampling.full_bounds", {item["code"] for item in validate_contract(bounds)["errors"]})

        parameter = copy.deepcopy(self.valid)
        other_mask = copy.deepcopy(parameter["masks"][1])
        other_mask["id"] = "aux-mask"
        other_mask["component_id"] = "aux-body"
        parameter["masks"].append(other_mask)
        parameter["parameters"][0]["evidence_mask_ids"] = ["aux-mask"]
        self.assertIn("lineage.parameter_mask_component", {item["code"] for item in validate_contract(parameter)["errors"]})

        combined = copy.deepcopy(self.valid)
        second_critical = copy.deepcopy(combined["masks"][1])
        second_critical["id"] = "critical-body-two"
        combined["masks"].append(second_critical)
        for result in combined["validation"]["results"]:
            result["mask_ids"].append("critical-body-two")
        self.assertIn("schema.max_items", {item["code"] for item in validate_contract(combined)["errors"]})

    def test_schema_integer_parity_and_signed_64_bit_semantics(self) -> None:
        integer_schema = {"type": "integer"}
        for value, valid in ((1.0, True), (-0.0, True), (1.5, False), (True, False)):
            with self.subTest(value=value):
                subset_valid = not validate_instance(value, integer_schema)
                self.assertEqual(subset_valid, valid)
                if importlib.util.find_spec("jsonschema") is not None:
                    from jsonschema import Draft202012Validator
                    self.assertEqual(not list(Draft202012Validator(integer_schema).iter_errors(value)), valid)

        integral = copy.deepcopy(self.valid)
        integral["source"]["point_count"] = 8.0
        self._assert_valid_diagnostic(integral, "pass")
        huge = copy.deepcopy(self.valid)
        huge["source"]["artifact"]["byte_count"] = 10**100
        self.assertFalse(validate_contract(huge)["contract_valid"])

    def test_schema_resource_caps_are_fail_closed_without_rejecting_normal_branch_probes(self) -> None:
        many_masks = copy.deepcopy(self.valid)
        template = many_masks["masks"][2]
        for index in range(128):
            item = copy.deepcopy(template)
            item["id"] = "extra-mask-%d" % index
            many_masks["masks"].append(item)
        subset = validate_instance(many_masks, self.schema)
        self.assertEqual(subset, [])
        if importlib.util.find_spec("jsonschema") is not None:
            from jsonschema import Draft202012Validator
            self.assertEqual(list(Draft202012Validator(self.schema).iter_errors(many_masks)), [])

        amplified = copy.deepcopy(self.valid)
        amplified["frames"] = [{} for _ in range(20_000)]
        issues = validate_instance(amplified, self.schema)
        self.assertTrue(issues)
        self.assertLessEqual(len(issues), 1)

        flat = validate_instance([0] * (MAX_INSTANCE_NODES + 1), {"type": "array"})
        self.assertEqual([item.code for item in flat], ["schema.resource_budget"])

    def test_strict_loader_enforces_streamed_size_cap_and_float_range(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            accepted = directory / "accepted.json"
            accepted.write_text("{}", encoding="ascii")
            rejected = directory / "rejected.json"
            rejected.write_text("{\"x\":0}", encoding="ascii")
            with mock.patch.object(contract_tools, "MAX_JSON_BYTES", 2):
                self.assertEqual(load_json_strict(accepted), {})
                with self.assertRaisesRegex(ValueError, "size cap"):
                    load_json_strict(rejected)
            subnormal = directory / "subnormal.json"
            subnormal.write_text("{\"value\":5e-324}", encoding="ascii")
            self.assertGreater(load_json_strict(subnormal)["value"], 0)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_contract_fifo_fails_cleanly_without_waiting_for_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fifo = Path(temporary) / "contract.json"
            os.mkfifo(fifo)
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_feature_contract.py"), str(fifo)],
                cwd=ROOT, check=False, capture_output=True, text=True, timeout=2,
            )
            self.assertEqual(completed.returncode, 2, completed.stderr + completed.stdout)
            self.assertNotIn("Traceback", completed.stderr + completed.stdout)
            payload = json.loads(completed.stdout)
            self.assertFalse(payload["ok"])
            self.assertNotIn(str(fifo), completed.stdout)

    def test_uncertainty_taxonomy_includes_model_terms_but_not_allowance(self) -> None:
        accepted = copy.deepcopy(self.valid)
        kinds = {item["kind"] for item in accepted["uncertainty"]["components"]}
        self.assertTrue({"scanner", "scale", "registration", "sampling", "segmentation", "model"}.issubset(kinds))
        self._assert_valid_diagnostic(accepted, "pass")

        rejected = copy.deepcopy(self.valid)
        rejected["uncertainty"]["components"][0]["kind"] = "manufacturing"
        report = validate_contract(rejected)
        self.assertFalse(report["contract_valid"])
        self.assertIn("schema.enum", {item["code"] for item in report["errors"]})

    def test_unc_private_path_is_rejected(self) -> None:
        contract = copy.deepcopy(self.valid)
        contract["frames"][0]["origin"] = "\\\\" + "internal-server" + "\\incoming\\scan.xyz"
        report = validate_contract(contract)
        self.assertIn("privacy.absolute_path", {item["code"] for item in report["errors"]})

    def test_embedded_private_paths_urls_and_hostnames_are_rejected(self) -> None:
        values = (
            "loaded from /" + "home/alice/customer/secret.step",
            "loaded from C:" + "\\Users\\alice\\private\\scan.xyz",
            "copied from https:" + "//internal-host/private/scan",
            "stored at s3:" + "//private-bucket/key",
            "reopened on internal-host.local",
            "reopened on 10.0.0.42",
            "reopened on 192.168.1.2:8080",
            "reopened on [fd00::1234]",
            "reopened on fd00::1234",
            "reopened on fe80::1%eth0",
            "reopened on localhost",
            "loaded from " + "\\Users\\alice\\scan",
            "loaded from " + ".." + "/incoming/scan.xyz",
            "loaded from " + "." + "/customer/scan.xyz",
            "loaded from " + "$" + "HOME/customer/scan.xyz",
        )
        for value in values:
            with self.subTest(value=value):
                contract = copy.deepcopy(self.valid)
                contract["authority"]["independent_reopen"]["notes"] = value
                codes = {item["code"] for item in validate_contract(contract)["errors"]}
                self.assertTrue({"privacy.absolute_path", "privacy.network_location"} & codes)

        secrets = (
            "password=hunter2",
            "api_key: sk-live-123456789",
            "AWS_ACCESS_KEY_ID=" + "AK" + "IAIOSFODNN7EXAMPLE",
            "Authorization: Bearer abc.def.ghi",
            "-----BEGIN " + "PRIVATE" + " KEY-----",
        )
        for value in secrets:
            with self.subTest(secret=value):
                contract = copy.deepcopy(self.valid)
                contract["authority"]["independent_reopen"]["notes"] = value
                self.assertIn("privacy.secret_value", {item["code"] for item in validate_contract(contract)["errors"]})

        versioned = copy.deepcopy(self.valid)
        versioned["authority"]["producer"]["tool_version"] = "1.2.3.4"
        versioned["authority"]["independent_reopen"]["tool_version"] = "7.8.1.1"
        self._assert_valid_diagnostic(versioned, "pass")

    def test_invalid_unknown_property_names_are_redacted_from_cli_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for key in (
                "pass" + "word=hunter2",
                "/" + "home/alice/customer/scan.xyz",
                "https:" + "//internal-host/private/scan",
            ):
                with self.subTest(key=key):
                    path = Path(temporary) / "invalid.json"
                    path.write_text(json.dumps({key: 1}), encoding="utf-8")
                    completed = subprocess.run(
                        [sys.executable, str(SCRIPTS / "validate_feature_contract.py"), str(path)],
                        cwd=ROOT,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
                    self.assertNotIn(key, completed.stdout + completed.stderr)
                    payload = json.loads(completed.stdout)
                    self.assertFalse(payload["contract_valid"])

    def test_contract_cli_argument_failures_are_one_clean_json_document(self) -> None:
        invocations = ((), ("--unknown-option",), ("--self-test", str(ASSETS / "feature-contract.example.json")))
        for arguments in invocations:
            with self.subTest(arguments=arguments):
                completed = subprocess.run(
                    [sys.executable, str(SCRIPTS / "validate_feature_contract.py"), *arguments],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 2, completed.stderr + completed.stdout)
                self.assertEqual(completed.stderr, "")
                payload = json.loads(completed.stdout)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["errors"][0]["code"], "argument_error")

    def test_contract_cli_rejects_extreme_and_non_json_numbers_as_one_clean_json_document(self) -> None:
        cases = {
            "huge-integer": '{"schema_version":"1.0.0","seed":' + ("9" * 100) + '}',
            "nan": '{"schema_version":"1.0.0","tolerance":NaN}',
            "infinity": '{"schema_version":"1.0.0","percentile":Infinity}',
            "float-overflow": '{"schema_version":"1.0.0","tolerance":1e9999}',
            "positive-underflow": '{"schema_version":"1.0.0","mean":1e-9999}',
            "negative-underflow": '{"schema_version":"1.0.0","mean":-1e-9999}',
            "duplicate-top": '{"contract_id":"attacker","contract_id":"canonical"}',
            "duplicate-nested": '{"outer":{"id":"first","id":"second"}}',
            "deep-nesting": ("[" * 2000) + "0" + ("]" * 2000),
        }
        with tempfile.TemporaryDirectory() as temporary:
            for name, content in cases.items():
                with self.subTest(name=name):
                    path = Path(temporary) / (name + ".json")
                    path.write_text(content, encoding="ascii")
                    completed = subprocess.run(
                        [sys.executable, str(SCRIPTS / "validate_feature_contract.py"), str(path)],
                        cwd=ROOT, check=False, capture_output=True, text=True,
                    )
                    self.assertEqual(completed.returncode, 2, completed.stderr + completed.stdout)
                    self.assertNotIn("Traceback", completed.stderr + completed.stdout)
                    payload, offset = json.JSONDecoder().raw_decode(completed.stdout)
                    self.assertFalse(completed.stdout[offset:].strip())
                    self.assertFalse(payload["ok"])
                    self.assertFalse(payload["contract_valid"])
                    self.assertNotIn(str(path), completed.stdout)

    def test_validator_self_test_entrypoint(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_feature_contract.py"), "--self-test"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertTrue(json.loads(completed.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
