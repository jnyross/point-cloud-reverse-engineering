from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_distributions  # noqa: E402
import compatibility_preflight  # noqa: E402
import validate_repo  # noqa: E402


class RouterContractTests(unittest.TestCase):
    @staticmethod
    def contract() -> dict:
        return json.loads((ROOT / "tests" / "router_contract.json").read_text(encoding="utf-8"))

    def test_terms_are_tokenized_not_substrings(self) -> None:
        rules = [{"value": "operate", "any_terms": ["build"]}]
        self.assertEqual(validate_repo.classify_request("build the part", rules, None), "operate")
        self.assertIsNone(validate_repo.classify_request("the builder is installed", rules, None))

    def test_phrases_are_normalized(self) -> None:
        rules = [{"value": "mesh", "any_phrases": ["mesh first"]}]
        self.assertEqual(validate_repo.classify_request("Use a mesh-first route", rules, None), "mesh")

    def test_skill_route_order_matches_machine_contract(self) -> None:
        contract = self.contract()
        expected = [validate_repo.ROUTE_LABELS[rule["value"]] for rule in contract["route_rules"]]
        actual = validate_repo.skill_route_labels(
            (ROOT / "skills" / "point-cloud-reverse-engineering" / "SKILL.md").read_text(encoding="utf-8")
        )
        self.assertEqual(actual, expected)
        self.assertEqual(contract["route_rules"][0]["value"], "read-only")

    def test_explanatory_question_remains_non_mutating(self) -> None:
        actual = validate_repo.classify_router_request(
            "How should we reconstruct this point cloud as editable STEP?",
            self.contract(),
        )
        self.assertEqual(actual, {"route": "read-only", "mutation": "none"})

    def test_polite_direct_request_can_authorize_change(self) -> None:
        actual = validate_repo.classify_router_request(
            "Can you reconstruct this point cloud as editable STEP?",
            self.contract(),
        )
        self.assertEqual(actual, {"route": "operate", "mutation": "scoped"})

    def test_effectful_intent_beats_advisory_vocabulary(self) -> None:
        actual = validate_repo.classify_router_request(
            "Inspect the fixed registration and rebuild only the rejected port.",
            self.contract(),
        )
        self.assertEqual(actual, {"route": "operate", "mutation": "scoped"})

    def test_linux_provisioning_is_an_effectful_route(self) -> None:
        actual = validate_repo.classify_router_request(
            "Diagnose the unavailable desktop route and provision the bounded Linux runtime.",
            self.contract(),
        )
        self.assertEqual(actual, {"route": "linux-open-source", "mutation": "scoped"})


class JsonSchemaSubsetTests(unittest.TestCase):
    def test_local_ref_and_closed_object(self) -> None:
        schema = {
            "$defs": {"positive": {"type": "number", "exclusiveMinimum": 0}},
            "type": "object",
            "required": ["value"],
            "additionalProperties": False,
            "properties": {"value": {"$ref": "#/$defs/positive"}},
        }
        self.assertEqual(validate_repo.validate_against_schema({"value": 2.5}, schema), [])
        self.assertTrue(validate_repo.validate_against_schema({"value": 0, "extra": 1}, schema))

    def test_one_of_requires_exactly_one_match(self) -> None:
        schema = {"oneOf": [{"type": "string"}, {"const": "x"}]}
        self.assertTrue(validate_repo.validate_against_schema("x", schema))
        self.assertEqual(validate_repo.validate_against_schema("y", schema), [])


class IntegrityTests(unittest.TestCase):
    def test_tree_digest_changes_with_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("one", encoding="utf-8")
            first = validate_repo.tree_digest(root)
            (root / "a.txt").write_text("two", encoding="utf-8")
            second = validate_repo.tree_digest(root)
            self.assertNotEqual(first, second)

    def test_privacy_canary_allows_documented_placeholders(self) -> None:
        examples = "/home/user/file /Users/user/file C:/Users/{user}/Fonts"
        self.assertFalse(any(pattern.search(examples) for pattern, _ in validate_repo.SECRET_PATTERNS))
        private_path = "/home/" + "alice/private"
        self.assertTrue(any(pattern.search(private_path) for pattern, _ in validate_repo.SECRET_PATTERNS))


class DistributionTests(unittest.TestCase):
    @staticmethod
    def _minimal_distribution(root: Path, common_files: list[str], archive_root: str = "safe-plugin") -> Path:
        (root / "skills" / "safe").mkdir(parents=True, exist_ok=True)
        (root / "skills" / "safe" / "SKILL.md").write_text("---\nname: safe\ndescription: safe\n---\n", encoding="utf-8")
        (root / "plugin.json").write_text(
            json.dumps({"name": "safe-plugin", "version": "1.0.0"}), encoding="utf-8"
        )
        config = {
            "schema_version": 1,
            "archive_root": archive_root,
            "common_files": common_files,
            "exclude_globs": ["**/*.map"],
            "profiles": {"core": {"description": "test", "skills": ["safe"]}},
        }
        config_path = root / "distribution.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return config_path

    @staticmethod
    def _rewrite_archive(source: Path, target: Path, replacements: dict[str, bytes]) -> None:
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as rewritten:
            for info in original.infolist():
                content = replacements.get(info.filename, original.read(info.filename))
                rewritten.writestr(
                    info,
                    content,
                    compress_type=info.compress_type,
                    compresslevel=9,
                )

    def test_core_archive_is_deterministic_and_source_map_free(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            archive_a = build_distributions.build_profile(Path(first), "core")
            archive_b = build_distributions.build_profile(Path(second), "core")
            self.assertEqual(archive_a.read_bytes(), archive_b.read_bytes())
            build_distributions.verify_archive(archive_a, "core")
            with zipfile.ZipFile(archive_a) as bundle:
                self.assertFalse(any(name.endswith(".map") for name in bundle.namelist()))
                self.assertIn("point-cloud-reverse-engineering/vendor-lock.json", bundle.namelist())
                manifest = json.loads(bundle.read(
                    "point-cloud-reverse-engineering/DISTRIBUTION-MANIFEST.json"
                ))
                recorded = {entry["path"] for entry in manifest["files"]}
                self.assertIn("README.md", recorded)
                self.assertIn("DISTRIBUTION-NOTICE.md", recorded)
                expected_compression, _ = build_distributions.compression_settings(build_distributions.load_config())
                self.assertTrue(all(info.compress_type == expected_compression for info in bundle.infolist()))

    def test_archive_verifier_rejects_tampered_identity_and_generated_docs(self) -> None:
        prefix = "point-cloud-reverse-engineering/"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = build_distributions.build_profile(root, "core")
            with zipfile.ZipFile(source) as bundle:
                manifest = json.loads(bundle.read(prefix + "DISTRIBUTION-MANIFEST.json"))
            manifest["plugin"] = "wrong-plugin"
            tampered_identity = root / "tampered-identity.zip"
            self._rewrite_archive(
                source,
                tampered_identity,
                {
                    prefix + "DISTRIBUTION-MANIFEST.json":
                        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
                },
            )
            with self.assertRaisesRegex(ValueError, "metadata mismatch"):
                build_distributions.verify_archive(tampered_identity, "core")

            with zipfile.ZipFile(source) as bundle:
                manifest = json.loads(bundle.read(prefix + "DISTRIBUTION-MANIFEST.json"))
            replacement = b"TAMPERED GENERATED README\n"
            for record in manifest["files"]:
                if record["path"] == "README.md":
                    record["bytes"] = len(replacement)
                    record["sha256"] = hashlib.sha256(replacement).hexdigest()
            tampered_docs = root / "tampered-docs.zip"
            self._rewrite_archive(
                source,
                tampered_docs,
                {
                    prefix + "DISTRIBUTION-MANIFEST.json":
                        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
                    prefix + "README.md": replacement,
                },
            )
            with self.assertRaisesRegex(ValueError, "differs from repository payload"):
                build_distributions.verify_archive(tampered_docs, "core")

    def test_full_profile_contains_every_skill(self) -> None:
        config = build_distributions.load_config()
        selected = set(build_distributions.selected_skills(config, "full"))
        available = {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}
        self.assertEqual(selected, available)

    def test_symlink_cannot_exfiltrate_checkout_secret(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            checkout = base / "checkout"
            checkout.mkdir()
            secret = base / "checkout-secret.txt"
            secret.write_text("must-not-enter-archive", encoding="utf-8")
            config_path = self._minimal_distribution(checkout, ["plugin.json"])
            (checkout / "skills" / "safe" / "leak.txt").symlink_to(secret)
            output = base / "out"
            with mock.patch.object(build_distributions, "ROOT", checkout), mock.patch.object(
                build_distributions, "CONFIG_PATH", config_path
            ):
                with self.assertRaisesRegex(ValueError, "symlink"):
                    build_distributions.build_profile(output, "core")
            self.assertEqual(list(output.glob("*.zip")) if output.exists() else [], [])

    def test_traversal_and_unsafe_archive_root_are_rejected_before_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            checkout = base / "checkout"
            checkout.mkdir()
            (base / "checkout-secret.txt").write_text("must-not-enter-archive", encoding="utf-8")
            output = base / "out"
            config_path = self._minimal_distribution(checkout, ["plugin.json", "../checkout-secret.txt"])
            with mock.patch.object(build_distributions, "ROOT", checkout), mock.patch.object(
                build_distributions, "CONFIG_PATH", config_path
            ):
                with self.assertRaisesRegex(ValueError, "unsafe path component"):
                    build_distributions.build_profile(output, "core")

            (checkout / "plugin.json").write_text(
                json.dumps({"name": "../checkout-secret", "version": "1.0.0"}), encoding="utf-8"
            )
            config_path = self._minimal_distribution(checkout, ["plugin.json"])
            (checkout / "plugin.json").write_text(
                json.dumps({"name": "../checkout-secret", "version": "1.0.0"}), encoding="utf-8"
            )
            with mock.patch.object(build_distributions, "ROOT", checkout), mock.patch.object(
                build_distributions, "CONFIG_PATH", config_path
            ):
                with self.assertRaisesRegex(ValueError, "unsafe path component"):
                    build_distributions.build_profile(output, "core")
            self.assertEqual(list(output.glob("*.zip")) if output.exists() else [], [])

            config_path = self._minimal_distribution(checkout, ["plugin.json"], archive_root="../escape")
            with mock.patch.object(build_distributions, "ROOT", checkout), mock.patch.object(
                build_distributions, "CONFIG_PATH", config_path
            ):
                with self.assertRaisesRegex(ValueError, "unsafe path component"):
                    build_distributions.build_profile(output, "core")


class CompatibilityTests(unittest.TestCase):
    def test_route_status_is_conservative(self) -> None:
        self.assertEqual(
            compatibility_preflight.route_status({"tool": {"status": "unknown"}}, ["tool"]),
            "unknown",
        )
        self.assertEqual(
            compatibility_preflight.route_status({"tool": {"status": "incompatible"}}, ["tool"]),
            "blocked_incompatible",
        )
        self.assertEqual(
            compatibility_preflight.route_status({"tool": {"status": "present_unverified"}}, ["tool"]),
            "available_unverified",
        )
        self.assertFalse(compatibility_preflight.strict_route_passes("available_unverified"))
        self.assertTrue(
            compatibility_preflight.strict_route_passes("available_unverified", allow_unverified=True)
        )

    def test_exact_blender_tuple_is_tested_and_outside_version_is_unknown(self) -> None:
        compatibility = json.loads((ROOT / "compatibility.json").read_text(encoding="utf-8"))
        detections = {
            "blender": {"status": "detected", "version": "5.2.0", "python": "3.13.13", "abi": "cpython-313"},
            "blender_python_abi": {"status": "detected", "version": "3.13.13", "abi": "cp313"},
            "cad_sketcher": {"status": "detected", "version": "0.30.0"},
            "agent_bridge": {"status": "detected", "version": "0.5.6"},
            "agent_bridge_command": {"status": "detected", "version": "0.5.6"},
        }
        assessed = compatibility_preflight.assess_components(detections, compatibility)
        self.assertTrue(all(item["status"] == "tested" for item in assessed.values()))

        detections["blender"] = {
            "status": "detected", "version": "5.3.0", "python": "3.13.13", "abi": "cpython-313"
        }
        assessed = compatibility_preflight.assess_components(detections, compatibility)
        self.assertEqual(assessed["blender"]["status"], "unknown")
        self.assertEqual(assessed["cad_sketcher"]["status"], "unknown")

    def test_missing_version_and_explicit_missing_cloudcompare_are_not_available(self) -> None:
        compatibility = json.loads((ROOT / "compatibility.json").read_text(encoding="utf-8"))
        assessed = compatibility_preflight.assess_components(
            {"cloudcompare": {"status": "present_unverified", "version": None}}, compatibility
        )
        self.assertEqual(assessed["cloudcompare"]["status"], "unknown")
        self.assertEqual(
            compatibility_preflight.probe_cloudcompare("/definitely/not/a/cloudcompare-binary")["status"],
            "missing",
        )

    def test_explicit_bridge_command_and_version_are_honored(self) -> None:
        completed = compatibility_preflight.subprocess.CompletedProcess(
            ["bridge", "--version"], 0, stdout="Blender Agent Bridge 0.5.6\n", stderr=""
        )
        with mock.patch.object(
            compatibility_preflight, "resolve_executable", return_value="/opt/tools/custom-bridge"
        ) as resolver, mock.patch.object(
            compatibility_preflight, "run_bounded", return_value=completed
        ):
            result = compatibility_preflight.probe_bridge_command("custom-bridge", execute=True)
        resolver.assert_called_once_with("custom-bridge", ("mcp-server-blender", "blender-mcp"))
        self.assertEqual(result["status"], "detected")
        self.assertEqual(result["version"], "0.5.6")

    def test_default_bridge_probe_is_metadata_only(self) -> None:
        with mock.patch.object(
            compatibility_preflight, "resolve_executable", return_value="/opt/tools/custom-bridge"
        ), mock.patch.object(compatibility_preflight, "run_bounded") as runner:
            result = compatibility_preflight.probe_bridge_command("custom-bridge")
        runner.assert_not_called()
        self.assertEqual(result["status"], "present_unverified")
        self.assertEqual(result["probe"], "metadata-only")

    def test_default_python_package_probe_does_not_import(self) -> None:
        with mock.patch.object(
            compatibility_preflight.importlib.util, "find_spec", return_value=object()
        ), mock.patch.object(
            compatibility_preflight.importlib.metadata,
            "packages_distributions",
            return_value={"example_package": ["example-distribution"]},
        ), mock.patch.object(
            compatibility_preflight.importlib.metadata, "version", return_value="1.2.3"
        ), mock.patch.object(compatibility_preflight, "run_bounded") as runner:
            result = compatibility_preflight.probe_python_package("example_package")
        runner.assert_not_called()
        self.assertEqual(result["status"], "present_unverified")
        self.assertFalse(result["runtime_verified"])

    def test_static_extension_manifest_cannot_be_promoted_to_tested(self) -> None:
        compatibility = json.loads((ROOT / "compatibility.json").read_text(encoding="utf-8"))
        static_extension = compatibility_preflight.probe_extension(
            [(Path("blender_manifest.toml"), {"id": "cad_sketcher", "version": "0.30.0"})],
            identifiers=("cad_sketcher",),
            blender_abi="cpython-313",
        )
        detections = {
            "blender": {
                "status": "detected",
                "version": "5.2.0",
                "python": "3.13.13",
                "abi": "cpython-313",
            },
            "blender_python_abi": {"status": "detected", "version": "3.13.13", "abi": "cp313"},
            "cad_sketcher": static_extension,
        }
        assessed = compatibility_preflight.assess_components(detections, compatibility)
        self.assertEqual(static_extension["status"], "present_unverified")
        self.assertEqual(assessed["cad_sketcher"]["status"], "present_unverified")

    def test_metadata_mode_discovers_extensions_without_guessing_active_series(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "blender"
            manifest = root / "5.2" / "extensions" / "user_default" / "cad_sketcher" / "blender_manifest.toml"
            manifest.parent.mkdir(parents=True)
            manifest.write_text('id = "cad_sketcher"\nversion = "0.30.0"\n', encoding="utf-8")
            with mock.patch.object(compatibility_preflight, "blender_config_roots", return_value=[root]):
                manifests = compatibility_preflight.extension_manifests(None)
        self.assertEqual(len(manifests), 1)
        result = compatibility_preflight.probe_extension(
            manifests,
            identifiers=("cad_sketcher",),
            blender_abi=None,
        )
        self.assertEqual(result["status"], "present_unverified")

    def test_explicit_dot_slash_executable_resolves_to_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "probe-tool"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            previous = Path.cwd()
            try:
                os.chdir(directory)
                resolved = compatibility_preflight.resolve_executable("./probe-tool", ())
            finally:
                os.chdir(previous)
        self.assertEqual(resolved, str(executable.resolve()))

    @unittest.skipUnless(os.name == "posix", "POSIX process groups are required")
    def test_timeout_terminates_the_probe_process_group(self) -> None:
        process = mock.Mock(pid=424242, returncode=-15)
        process.communicate.side_effect = [
            compatibility_preflight.subprocess.TimeoutExpired(["probe"], 0.01),
            ("", ""),
        ]
        with mock.patch.object(
            compatibility_preflight.subprocess, "Popen", return_value=process
        ) as popen, mock.patch.object(compatibility_preflight.os, "killpg") as killpg:
            result = compatibility_preflight.run_bounded(["probe"], timeout=0.01)
        self.assertIsNone(result)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertIs(popen.call_args.kwargs["stdin"], compatibility_preflight.subprocess.DEVNULL)
        killpg.assert_called_once_with(process.pid, compatibility_preflight.signal.SIGTERM)

    def test_blender_routes_require_the_bridge_command(self) -> None:
        compatibility = json.loads((ROOT / "compatibility.json").read_text(encoding="utf-8"))
        self.assertIn("agent_bridge_command", compatibility["routes"]["blender-ai-workbench"]["required_components"])
        self.assertFalse(compatibility["routes"]["hybrid-blender-brep"]["tested"])

    def test_static_manifest_is_machine_neutral(self) -> None:
        text = (ROOT / "compatibility.json").read_text(encoding="utf-8")
        data = json.loads(text)
        self.assertEqual(data["tested_stack"]["blender"], "5.2.0 LTS")
        self.assertEqual(data["tested_stack"]["agent_bridge_command"], "0.5.6")
        self.assertNotIn("/home/", text)
        self.assertNotIn("/Users/", text)


class WorkflowTests(unittest.TestCase):
    @staticmethod
    def _block_scripts(text: str) -> list[str]:
        lines = text.splitlines()
        scripts: list[str] = []
        index = 0
        while index < len(lines):
            match = re.match(r"^(\s*)run:\s*\|\s*$", lines[index])
            if not match:
                index += 1
                continue
            base = len(match.group(1))
            index += 1
            block: list[str] = []
            while index < len(lines):
                line = lines[index]
                indentation = len(line) - len(line.lstrip())
                if line.strip() and indentation <= base:
                    break
                block.append(line[base + 2:] if line.strip() else "")
                index += 1
            scripts.append("\n".join(block) + "\n")
        return scripts

    def test_actions_are_immutable_and_checkouts_do_not_persist_credentials(self) -> None:
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            uses = re.findall(r"(?m)^\s*-?\s*uses:\s*([^\s#]+)", text)
            self.assertTrue(uses, path)
            for action in uses:
                self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$", f"mutable action ref in {path}: {action}")
            checkout_count = text.count("uses: actions/checkout@")
            self.assertEqual(text.count("persist-credentials: false"), checkout_count, path)

    def test_write_token_job_is_minimal_and_release_push_is_atomic(self) -> None:
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        publish = text.split("\n  publish:\n", 1)[1]
        authenticated = publish.split("      - name: atomically publish or repair GitHub release\n", 1)[1]
        self.assertIn("contents: write", publish)
        self.assertNotIn("pip install", publish)
        self.assertNotIn("scripts/", publish)
        self.assertNotIn("python3", authenticated)
        self.assertIn("git push --atomic", authenticated)
        self.assertIn("gh release download", authenticated)
        self.assertIn("gh release upload", authenticated)
        self.assertIn("gh release create", authenticated)
        self.assertIn("invalid SHA256SUMS entries", publish)
        self.assertIn("include-hidden-files: true", text)
        self.assertIn("prepared/.codex-plugin/plugin.json", publish)

    def test_standalone_quality_workflow_does_not_duplicate_main_gate(self) -> None:
        text = (ROOT / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")
        trigger = text.split("permissions:", 1)[0]
        self.assertIn("pull_request:", trigger)
        self.assertIn("workflow_dispatch:", trigger)
        self.assertNotIn("push:", trigger)
        self.assertIn('python-version: ["3.11", "3.13"]', text)
        self.assertIn("python-version: ${{ matrix.python-version }}", text)
        self.assertIn("if: matrix.python-version == '3.13'", text)

    @unittest.skipUnless(shutil.which("bash"), "bash is required to parse workflow scripts")
    def test_multiline_workflow_shell_blocks_parse(self) -> None:
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            for index, script in enumerate(self._block_scripts(text), 1):
                completed = subprocess.run(
                    ["bash", "-n"], input=script, text=True, capture_output=True, check=False
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    f"{path} shell block {index}: {completed.stderr}",
                )


if __name__ == "__main__":
    unittest.main()
