from __future__ import annotations

import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "point-cloud-reverse-engineering"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pcre_tools.cloud as cloud_tools  # noqa: E402
from pcre_tools.cloud import (  # noqa: E402
    CloudFormatError,
    MAX_MASK_DEFINITIONS,
    MAX_SAMPLE_POINTS,
    STDLIB_MAX_PAIR_EVALUATIONS,
    analyze_cloud,
    bidirectional_distance,
    determinant3,
    distance_statistics,
    load_mask,
    scan_and_sample,
    transform_bounds_canary,
)


CUBE = [
    (0.0, 0.0, 0.0),
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (1.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
    (1.0, 0.0, 1.0),
    (0.0, 1.0, 1.0),
    (1.0, 1.0, 1.0),
]


def write_cloud(path: Path, points: list[tuple[float, float, float]]) -> None:
    path.write_text("".join("%.6f %.6f %.6f\n" % point for point in points), encoding="ascii")


class PointCloudEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.cloud = self.directory / "cube.xyz"
        write_cloud(self.cloud, CUBE)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run_tool(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "point_cloud_evidence.py"), *arguments],
            cwd=ROOT, check=False, capture_output=True, text=True,
        )

    def _assert_clean_json_error(self, completed: subprocess.CompletedProcess[str], *private_paths: Path) -> dict:
        self.assertEqual(completed.returncode, 2, completed.stderr + completed.stdout)
        self.assertNotIn("Traceback", completed.stderr + completed.stdout)
        decoder = json.JSONDecoder()
        payload, offset = decoder.raw_decode(completed.stdout)
        self.assertFalse(completed.stdout[offset:].strip(), completed.stdout)
        self.assertFalse(payload["operation_ok"])
        self.assertEqual(payload["evidence_status"], "not-evaluated")
        for path in private_paths:
            self.assertNotIn(str(path), completed.stdout)
        return payload

    def test_cli_argument_failures_are_one_clean_json_document(self) -> None:
        invocations = ((), ("--bogus",), ("unknown-command",), ("fingerprint",))
        for arguments in invocations:
            with self.subTest(arguments=arguments):
                completed = self._run_tool(*arguments)
                payload = self._assert_clean_json_error(completed)
                self.assertEqual(completed.stderr, "")
                self.assertEqual(payload["error"]["code"], "argument_error")

    def test_fingerprint_count_bounds_and_canonical_hash_are_stable(self) -> None:
        first = analyze_cloud(self.cloud)
        second = analyze_cloud(self.cloud)
        self.assertEqual(first, second)
        self.assertEqual(first["point_count"], 8)
        self.assertEqual(first["bounds"], {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]})
        self.assertRegex(first["artifact"]["sha256"], r"^[0-9a-f]{64}$")

    def test_role_separated_sampling_is_deterministic_and_bounded(self) -> None:
        first_report, first = scan_and_sample(self.cloud, 4, 17, "measurement")
        repeat_report, repeat = scan_and_sample(self.cloud, 4, 17, "measurement")
        display_report, display = scan_and_sample(self.cloud, 4, 17, "display")
        self.assertEqual(first, repeat)
        self.assertEqual(first_report["sample"]["canonical_points_sha256"], repeat_report["sample"]["canonical_points_sha256"])
        self.assertEqual(len(first), 4)
        self.assertNotEqual(first_report["sample"]["canonical_points_sha256"], display_report["sample"]["canonical_points_sha256"])
        self.assertNotEqual(first, display)

    def test_true_full_sample_preserves_source_order_and_canonical_hash(self) -> None:
        report, points = scan_and_sample(self.cloud, len(CUBE), 19, "measurement", frame="source")
        self.assertEqual(report["sample"]["method"], "full")
        self.assertEqual(report["sample"]["parameters"], {})
        self.assertEqual(points, CUBE)
        self.assertEqual(report["sample"]["canonical_points_sha256"], report["source"]["canonical_points_sha256"])
        self.assertEqual(report["sample"]["frame"], "source")
        self.assertEqual(report["sample"]["bounds"]["frame"], "source")
        self.assertEqual(report["sample"]["source_sha256"], report["source"]["artifact"]["sha256"])
        self.assertEqual(report["sample"]["source_point_count"], len(CUBE))

    def test_masked_all_eligible_sample_is_not_mislabeled_full(self) -> None:
        mask = {
            "frame": "source",
            "include": [{"type": "aabb", "min": [-1, -1, -1], "max": [2, 2, 2]}],
            "exclude": [],
        }
        report, points = scan_and_sample(self.cloud, len(CUBE), 0, "measurement", mask=mask, frame="source")
        self.assertEqual(points, CUBE)
        self.assertEqual(report["sample"]["method"], "masked-hash-rank")
        self.assertEqual(report["sample"]["parameters"]["eligible_count"], len(CUBE))
        self.assertRegex(report["sample"]["parameters"]["mask_sha256"], r"^[0-9a-f]{64}$")

    def test_mask_is_applied_before_sampling(self) -> None:
        mask = {"frame": "source", "include": [{"type": "aabb", "min": [0, 0, 0], "max": [0, 1, 1]}], "exclude": []}
        report, points = scan_and_sample(self.cloud, 8, 0, "measurement", mask=mask, frame="source")
        self.assertEqual(report["eligible_point_count"], 4)
        self.assertEqual(report["observed_coverage_percent"], 50)
        self.assertTrue(all(point[0] == 0 for point in points))

    def test_nontrivial_determinant_and_transformed_bounds(self) -> None:
        matrix = [
            0, -2, 0, 10,
            3, 0, 0, 20,
            0, 0, 4, 30,
            0, 0, 0, 1,
        ]
        inverse = [
            0, 1 / 3, 0, -20 / 3,
            -1 / 2, 0, 0, 5,
            0, 0, 1 / 4, -7.5,
            0, 0, 0, 1,
        ]
        self.assertEqual(determinant3(matrix), 24)
        report = transform_bounds_canary(matrix, inverse, (0, 0, 0), (1, 2, 3))
        self.assertTrue(report["ok"])
        self.assertEqual(report["transformed_bounds"]["min"], [6, 20, 30])
        self.assertEqual(report["transformed_bounds"]["max"], [10, 23, 42])

        projective = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1e-11, 0, 0, 1]
        projective_inverse = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -1e-11, 0, 0, 1]
        projective_report = transform_bounds_canary(
            projective, projective_inverse, (0, 0, 0), (1e12, 1, 1)
        )
        self.assertFalse(projective_report["ok"])
        self.assertFalse(projective_report["homogeneous_last_row_valid"])

    def test_bidirectional_distance_reports_honest_point_metric(self) -> None:
        shifted = [(x + 0.1, y, z) for x, y, z in CUBE]
        report = bidirectional_distance(CUBE, shifted, 0.15, [50, 95, 98, 99], 3)
        self.assertEqual(report["metric_scope"], "bounded-point-sample-canary")
        self.assertEqual(len(report["directions"]), 2)
        for direction in report["directions"]:
            self.assertEqual(direction["metric_kind"], "point-to-point")
            self.assertEqual(direction["signedness"], "unsigned")
            self.assertAlmostEqual(direction["mean"], 0.1)
            self.assertEqual(direction["within_tolerance_percent"], 100)
            self.assertEqual(direction["realizability_certificate"]["version"], "normalized-blocks-v1")

    def test_distance_backends_and_summaries_preserve_tiny_and_large_finite_magnitudes(self) -> None:
        backends = ["stdlib"]
        if importlib.util.find_spec("scipy") is not None:
            backends.append("scipy")
        for backend in backends:
            with self.subTest(backend=backend, magnitude="tiny"):
                tiny = distance_statistics(
                    [(0.0, 0.0, 0.0)], [(1e-200, 0.0, 0.0)], 1e-210,
                    [50, 95, 98, 99], 1, backend,
                )
                self.assertEqual(tiny["within_tolerance_percent"], 0)
                self.assertEqual(tiny["mean"], 1e-200)
                self.assertEqual(tiny["rms"], 1e-200)
                self.assertEqual(tiny["maximum"], 1e-200)
            with self.subTest(backend=backend, magnitude="large"):
                large = distance_statistics(
                    [(0.0, 0.0, 0.0)], [(1e200, 0.0, 0.0)], 1e199,
                    [50, 95, 98, 99], 1, backend,
                )
                self.assertEqual(large["within_tolerance_percent"], 0)
                self.assertTrue(math.isfinite(large["mean"]))
                self.assertEqual(large["mean"], 1e200)
                self.assertEqual(large["rms"], 1e200)
                self.assertEqual(large["maximum"], 1e200)

        repeated_large = distance_statistics(
            [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0)], [(1e308, 0.0, 0.0)], 1e307,
            [50, 95, 98, 99], 1, "stdlib",
        )
        self.assertEqual(repeated_large["mean"], 1e308)
        self.assertEqual(repeated_large["rms"], 1e308)

        unrepresentable = [(0.0, 0.0, 0.0)] * 99_999 + [(5e-324, 0.0, 0.0)]
        for backend in backends:
            with self.subTest(backend=backend, magnitude="unrepresentable-moment"):
                with self.assertRaisesRegex(OverflowError, "underflow"):
                    distance_statistics(
                        unrepresentable,
                        [(0.0, 0.0, 0.0)],
                        5e-324,
                        [50, 95, 98, 99],
                        256,
                        backend,
                    )

    def test_stdlib_distance_has_a_hard_pair_budget(self) -> None:
        side = int(math.sqrt(STDLIB_MAX_PAIR_EVALUATIONS / 2)) + 1
        repeated = [(0.0, 0.0, 0.0)] * side
        with self.assertRaisesRegex(ValueError, "hard .*pair.*work budget"):
            bidirectional_distance(repeated, repeated, 0.1, [95], 256)

    def test_sample_count_has_a_backend_independent_hard_cap(self) -> None:
        with self.assertRaisesRegex(ValueError, "hard .*point memory cap"):
            scan_and_sample(self.cloud, MAX_SAMPLE_POINTS + 1, 0, "measurement")

    def test_nonfinite_transform_inputs_fail_before_json_output(self) -> None:
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        with self.assertRaisesRegex(ValueError, "finite"):
            transform_bounds_canary(identity, identity, (0, 0, 0), (1, math.inf, 1))
        identity[0] = math.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            transform_bounds_canary(identity, [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], (0, 0, 0), (1, 1, 1))

    def test_masks_reject_nonfinite_boolean_and_reversed_geometry(self) -> None:
        bad_masks = [
            {"frame": "source", "include": [{"type": "aabb", "min": [2, 0, 0], "max": [1, 1, 1]}], "exclude": []},
            {"frame": "source", "include": [{"type": "sphere", "center": [0, True, 0], "radius": 1}], "exclude": []},
            {"frame": "source", "include": [{"type": "sphere", "center": [0, 0, 0], "radius": float("inf")}], "exclude": []},
        ]
        for index, mask in enumerate(bad_masks):
            path = self.directory / ("bad-mask-%d.json" % index)
            path.write_text(json.dumps(mask), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_mask(path)

    def test_mask_frame_must_match_explicit_comparison_frame(self) -> None:
        mask = {"frame": "cad", "include": [], "exclude": []}
        with self.assertRaisesRegex(ValueError, "frame does not match"):
            scan_and_sample(self.cloud, 4, 0, "measurement", mask=mask, frame="source")

        mask_path = self.directory / "cad-mask.json"
        mask_path.write_text(json.dumps(mask), encoding="utf-8")
        destination = self.directory / "sample.xyz"
        completed = self._run_tool(
            "sample", str(self.cloud), "--role", "measurement", "--count", "4",
            "--frame", "source", "--mask", str(mask_path), "--output", str(destination),
        )
        self._assert_clean_json_error(completed, self.cloud, mask_path, destination)

    def test_mask_definition_count_has_a_hard_cap(self) -> None:
        definition = {"type": "sphere", "center": [0, 0, 0], "radius": 1}
        mask = {"frame": "source", "include": [definition] * (MAX_MASK_DEFINITIONS + 1), "exclude": []}
        with self.assertRaisesRegex(ValueError, "definition cap"):
            scan_and_sample(self.cloud, 4, 0, "measurement", mask=mask, frame="source")

    def test_negative_skip_lines_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            analyze_cloud(self.cloud, skip_lines=-1)

    def test_sample_cli_preserves_existing_destination_without_overwrite(self) -> None:
        destination = self.directory / "sample.xyz"
        destination.write_text("sentinel\n", encoding="ascii")
        completed = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "point_cloud_evidence.py"), "sample", str(self.cloud),
                "--role", "display", "--count", "4", "--frame", "source", "--output", str(destination),
            ],
            cwd=ROOT, check=False, capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(destination.read_text(encoding="ascii"), "sentinel\n")
        self.assertNotIn(str(destination), completed.stdout)

    def test_sample_cli_overwrite_is_explicit_and_atomic(self) -> None:
        destination = self.directory / "replace.xyz"
        destination.write_text("sentinel\n", encoding="ascii")
        completed = self._run_tool(
            "sample", str(self.cloud), "--role", "display", "--count", "4", "--frame", "source",
            "--output", str(destination), "--overwrite",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["operation_ok"])
        self.assertEqual(payload["evidence_status"], "not-evaluated")
        self.assertNotEqual(destination.read_text(encoding="ascii"), "sentinel\n")
        self.assertNotIn(str(self.cloud), completed.stdout)
        self.assertNotIn(str(destination), completed.stdout)

    def test_preplanted_legacy_temp_symlink_is_neither_followed_nor_unlinked(self) -> None:
        destination = self.directory / "sample.xyz"
        victim = self.directory / "victim.txt"
        victim.write_text("do-not-touch\n", encoding="ascii")
        planted = self.directory / (destination.name + ".tmp-" + str(os.getpid()))
        planted.symlink_to(victim)
        completed = self._run_tool(
            "sample", str(self.cloud), "--role", "measurement", "--count", "4", "--frame", "source",
            "--output", str(destination),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertEqual(victim.read_text(encoding="ascii"), "do-not-touch\n")
        self.assertTrue(planted.is_symlink())
        self.assertTrue(destination.is_file())

    def test_source_identity_and_hardlink_destinations_are_rejected_even_with_overwrite(self) -> None:
        original = self.cloud.read_bytes()
        same = self._run_tool(
            "sample", str(self.cloud), "--role", "measurement", "--count", "4", "--frame", "source",
            "--output", str(self.cloud), "--overwrite",
        )
        self._assert_clean_json_error(same, self.cloud)
        self.assertEqual(self.cloud.read_bytes(), original)

        hardlink = self.directory / "source-hardlink.xyz"
        os.link(self.cloud, hardlink)
        linked = self._run_tool(
            "sample", str(self.cloud), "--role", "measurement", "--count", "4", "--frame", "source",
            "--output", str(hardlink), "--overwrite",
        )
        self._assert_clean_json_error(linked, self.cloud, hardlink)
        self.assertEqual(self.cloud.read_bytes(), original)
        self.assertTrue(os.path.samefile(self.cloud, hardlink))

    def test_overwrite_publication_fails_closed_if_parent_path_is_relocated(self) -> None:
        victim_directory = self.directory / "victim"
        output_directory = self.directory / "out"
        victim_directory.mkdir()
        output_directory.mkdir()
        source = victim_directory / "source.xyz"
        destination = output_directory / "source.xyz"
        source.write_text("9 9 9\n", encoding="ascii")
        destination.write_text("sentinel\n", encoding="ascii")
        original_source = source.read_bytes()
        original_replace = cloud_tools.os.replace

        def relocate_parent(source_name, destination_name, *args, **kwargs):
            moved_output = self.directory / "out-old"
            output_directory.rename(moved_output)
            os.link(moved_output / source_name, victim_directory / source_name)
            output_directory.symlink_to(victim_directory, target_is_directory=True)
            return original_replace(source_name, destination_name, *args, **kwargs)

        with mock.patch.object(cloud_tools.os, "replace", side_effect=relocate_parent):
            with self.assertRaisesRegex(RuntimeError, "parent changed"):
                cloud_tools.write_xyz(destination, [(1.0, 2.0, 3.0)], overwrite=True, source_path=source)
        self.assertEqual(source.read_bytes(), original_source)

    def test_nonfinite_input_fails_closed(self) -> None:
        bad = self.directory / "bad.xyz"
        bad.write_text("0 0 0\nNaN 1 2\n", encoding="ascii")
        with self.assertRaises(CloudFormatError):
            analyze_cloud(bad)

    def test_source_mutation_is_detected_for_analysis_and_sampling(self) -> None:
        original_iter = cloud_tools._iter_points_fd

        def mutating_iter(descriptor: int, *args, **kwargs):
            captured = list(original_iter(descriptor, *args, **kwargs))
            write_cloud(self.cloud, [(x + 10, y, z) for x, y, z in CUBE])
            yield from captured

        with mock.patch.object(cloud_tools, "_iter_points_fd", side_effect=mutating_iter):
            with self.assertRaisesRegex(CloudFormatError, "source content changed"):
                analyze_cloud(self.cloud)

        write_cloud(self.cloud, CUBE)
        with mock.patch.object(cloud_tools, "_iter_points_fd", side_effect=mutating_iter):
            with self.assertRaisesRegex(CloudFormatError, "source content changed"):
                scan_and_sample(self.cloud, 4, 0, "measurement")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_path_swap_to_fifo_after_open_uses_pinned_source_and_fails_without_hanging(self) -> None:
        original_detect = cloud_tools._detect_format_fd

        def swap_to_fifo(path: Path, requested: str, descriptor: int) -> str:
            path.unlink()
            os.mkfifo(path)
            return original_detect(path, requested, descriptor)

        with mock.patch.object(cloud_tools, "_detect_format_fd", side_effect=swap_to_fifo):
            with self.assertRaisesRegex(CloudFormatError, "source content changed"):
                analyze_cloud(self.cloud)

        self.cloud.unlink()
        write_cloud(self.cloud, CUBE)
        with mock.patch.object(cloud_tools, "_detect_format_fd", side_effect=swap_to_fifo):
            with self.assertRaisesRegex(CloudFormatError, "source content changed"):
                scan_and_sample(self.cloud, 4, 0, "measurement")

    def test_underflow_and_overlong_lines_fail_as_clean_path_redacted_json(self) -> None:
        underflow = self.directory / "underflow.xyz"
        underflow.write_text("-1e-9999 0 0\n", encoding="ascii")
        fingerprint = self._run_tool("fingerprint", str(underflow))
        self._assert_clean_json_error(fingerprint, underflow)
        distance = self._run_tool(
            "distance", str(self.cloud), str(underflow), "--frame", "source", "--tolerance", "0.1",
            "--max-a", "8", "--max-b", "8",
        )
        self._assert_clean_json_error(distance, self.cloud, underflow)

        smallest = self.directory / "smallest.xyz"
        smallest.write_text("5e-324 0 0\n", encoding="ascii")
        self.assertGreater(analyze_cloud(smallest)["bounds"]["min"][0], 0)

        overlong = self.directory / "overlong.xyz"
        overlong.write_text("0 " + ("1" * (cloud_tools.MAX_CLOUD_LINE_CHARS + 1)) + " 0\n", encoding="ascii")
        self._assert_clean_json_error(self._run_tool("fingerprint", str(overlong)), overlong)

        underscore = self.directory / "underscore.xyz"
        underscore.write_text("1_0 0 0\n", encoding="ascii")
        self._assert_clean_json_error(self._run_tool("fingerprint", str(underscore)), underscore)

    def test_csv_missing_coordinate_is_rejected_without_column_shift(self) -> None:
        malformed = self.directory / "missing-y.csv"
        malformed.write_text("1,,3,99\n", encoding="ascii")
        completed = self._run_tool("fingerprint", str(malformed))
        self._assert_clean_json_error(completed, malformed)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_nonregular_sources_fail_without_waiting_for_a_writer(self) -> None:
        fifo = self.directory / "source.xyz"
        os.mkfifo(fifo)
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "point_cloud_evidence.py"), "fingerprint", str(fifo)],
            cwd=ROOT, check=False, capture_output=True, text=True, timeout=2,
        )
        self._assert_clean_json_error(completed, fifo)

    def test_malformed_ply_inputs_fail_as_one_path_redacted_json_document(self) -> None:
        cases = {
            "version": "ply\nformat ascii 2.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n",
            "property": "ply\nformat ascii 1.0\nelement vertex 1\nproperty float\nend_header\n0 0 0\n",
            "tokens": "ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 0 7\n",
            "extra-vertex": "ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n1 1 1\n",
            "missing-face": (
                "ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\n"
                "element face 1\nproperty list uchar int vertex_indices\nend_header\n0 0 0\n"
            ),
            "bad-extra-property": (
                "ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\n"
                "property uchar red\nend_header\n0 0 0 not-an-integer\n"
            ),
            "bad-face-list": (
                "ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\n"
                "element face 1\nproperty list uchar int vertex_indices\nend_header\n0 0 0\n3 0 1\n"
            ),
            "underscore-scalar": (
                "ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\n"
                "property uchar red\nend_header\n0 0 0 1_0\n"
            ),
            "underscore-list": (
                "ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\n"
                "element face 1\nproperty list uchar int vertex_indices\nend_header\n0 0 0\n3 0 1 2_0\n"
            ),
            "underscore-element-count": (
                "ply\nformat ascii 1.0\nelement vertex 1_0\nproperty float x\nproperty float y\nproperty float z\n"
                "end_header\n" + ("0 0 0\n" * 10)
            ),
        }
        for name, content in cases.items():
            with self.subTest(name=name):
                path = self.directory / (name + ".ply")
                path.write_text(content, encoding="ascii")
                completed = self._run_tool("fingerprint", str(path))
                self._assert_clean_json_error(completed, path)

    def test_ascii_ply_with_well_formed_face_properties_is_supported(self) -> None:
        path = self.directory / "triangle.ply"
        path.write_text(
            "ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\n"
            "element face 1\nproperty list uchar int vertex_indices\nend_header\n0 0 0\n1 0 0\n0 1 0\n3 0 1 2\n",
            encoding="ascii",
        )
        report = analyze_cloud(path)
        self.assertEqual(report["point_count"], 3)

        zero_face = self.directory / "point-with-zero-faces.ply"
        zero_face.write_text(
            "ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\n"
            "element face 0\nproperty list uchar int vertex_indices\nend_header\n2 3 4\n",
            encoding="ascii",
        )
        zero_report = analyze_cloud(zero_face)
        self.assertEqual(zero_report["point_count"], 1)
        self.assertEqual(zero_report["bounds"], {"min": [2.0, 3.0, 4.0], "max": [2.0, 3.0, 4.0]})

    def test_nonfinite_distance_options_fail_closed_without_partial_json(self) -> None:
        for option, value in (("--tolerance", "nan"), ("--tolerance", "inf"), ("--percentiles", "nan")):
            with self.subTest(option=option, value=value):
                arguments = [
                    "distance", str(self.cloud), str(self.cloud), "--frame", "source", "--tolerance", "0.1",
                    "--max-a", "8", "--max-b", "8",
                ]
                if option == "--tolerance":
                    arguments[arguments.index("--tolerance") + 1] = value
                else:
                    arguments.extend([option, value])
                completed = self._run_tool(*arguments)
                self._assert_clean_json_error(completed, self.cloud)

    def test_enormous_json_mask_integer_fails_closed(self) -> None:
        mask_path = self.directory / "huge-mask.json"
        mask_path.write_text(
            '{"frame":"source","include":[{"type":"sphere","center":[0,0,0],"radius":' + ("9" * 100) + '}],"exclude":[]}',
            encoding="ascii",
        )
        destination = self.directory / "huge-sample.xyz"
        completed = self._run_tool(
            "sample", str(self.cloud), "--role", "measurement", "--count", "4", "--frame", "source",
            "--mask", str(mask_path), "--output", str(destination),
        )
        self._assert_clean_json_error(completed, self.cloud, mask_path, destination)

    def test_unknown_mask_property_is_redacted_from_cli_error(self) -> None:
        private_key = "pass" + "word=hunter2"
        masks = (
            {"frame": "source", "include": [], "exclude": [], private_key: 1},
            {
                "frame": "source",
                "include": [{"type": "sphere", "center": [0, 0, 0], "radius": 1, private_key: True}],
                "exclude": [],
            },
        )
        for index, mask in enumerate(masks):
            with self.subTest(index=index):
                mask_path = self.directory / ("private-key-mask-%d.json" % index)
                mask_path.write_text(json.dumps(mask), encoding="utf-8")
                destination = self.directory / ("private-key-sample-%d.xyz" % index)
                completed = self._run_tool(
                    "sample", str(self.cloud), "--role", "measurement", "--count", "4", "--frame", "source",
                    "--mask", str(mask_path), "--output", str(destination),
                )
                self._assert_clean_json_error(completed, self.cloud, mask_path, destination)
                self.assertNotIn(private_key, completed.stdout + completed.stderr)

    def test_transform_overflow_reflection_and_roundtrip_fail_closed(self) -> None:
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        overflow = identity.copy()
        overflow[0] = 1e308
        inverse_overflow = identity.copy()
        inverse_overflow[0] = 1e-308
        completed = self._run_tool(
            "transform-canary", "--matrix", *[str(value) for value in overflow],
            "--inverse-matrix", *[str(value) for value in inverse_overflow],
            "--bounds", "0", "0", "0", "1", "1", "1",
        )
        self._assert_clean_json_error(completed)

        reflection = identity.copy()
        reflection[0] = -1
        reflected = transform_bounds_canary(reflection, reflection, (0, 0, 0), (1, 1, 1))
        self.assertFalse(reflected["ok"])
        self.assertFalse(reflected["reflection_documented"])
        allowed = transform_bounds_canary(reflection, reflection, (0, 0, 0), (1, 1, 1), reflection_allowed=True)
        self.assertTrue(allowed["ok"])

        bad_inverse = identity.copy()
        bad_inverse[3] = 1
        roundtrip = transform_bounds_canary(identity, bad_inverse, (0, 0, 0), (1, 1, 1))
        self.assertFalse(roundtrip["ok"])
        self.assertGreater(roundtrip["round_trip_max"], roundtrip["round_trip_tolerance"])

    def test_cli_fingerprint_and_distance(self) -> None:
        shifted_path = self.directory / "shifted.xyz"
        write_cloud(shifted_path, [(x + 0.1, y, z) for x, y, z in CUBE])
        fingerprint = subprocess.run(
            [sys.executable, str(SCRIPTS / "point_cloud_evidence.py"), "fingerprint", str(self.cloud)],
            cwd=ROOT, check=False, capture_output=True, text=True,
        )
        self.assertEqual(fingerprint.returncode, 0, fingerprint.stderr + fingerprint.stdout)
        self.assertNotIn(str(self.cloud), fingerprint.stdout)
        self.assertEqual(json.loads(fingerprint.stdout)["point_count"], 8)
        distance = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "point_cloud_evidence.py"), "distance",
                str(self.cloud), str(shifted_path), "--frame", "source", "--tolerance", "0.001",
                "--max-a", "8", "--max-b", "8", "--batch-size", "3",
            ],
            cwd=ROOT, check=False, capture_output=True, text=True,
        )
        self.assertEqual(distance.returncode, 0, distance.stderr + distance.stdout)
        payload = json.loads(distance.stdout)
        self.assertTrue(payload["operation_ok"])
        self.assertEqual(payload["evidence_status"], "not-evaluated")
        self.assertFalse(payload["registration_performed"])
        self.assertEqual(payload["directions"][0]["backend"], "stdlib-bounded")
        self.assertTrue(all(direction["within_tolerance_percent"] == 0 for direction in payload["directions"]))


if __name__ == "__main__":
    unittest.main()
