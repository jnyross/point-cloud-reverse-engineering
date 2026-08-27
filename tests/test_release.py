from __future__ import annotations

import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release  # noqa: E402


class ReleaseTests(unittest.TestCase):
    def test_log_parser_preserves_body_and_footer(self) -> None:
        with mock.patch.object(
            release,
            "git",
            side_effect=["benchmark\nv0.5.0\nv0.6.0-rc1", "fix: subject\n\nBREAKING CHANGE: body contract\x00"],
        ) as git:
            messages = release.commits_since_last_tag("0.5.0")
        self.assertEqual(messages, ["fix: subject\n\nBREAKING CHANGE: body contract"])
        self.assertEqual(release.bump_level(messages), "major")
        self.assertEqual(
            git.call_args_list,
            [
                mock.call("tag", "--merged", "HEAD", "--list"),
                mock.call("log", "--format=%B%x00", "v0.5.0..HEAD"),
            ],
        )

    def test_unrelated_tag_cannot_hide_a_feature_commit(self) -> None:
        with mock.patch.object(
            release,
            "git",
            side_effect=["benchmark-latest\nv0.5.0", "feat: add Blender route\x00fix: docs\x00"],
        ):
            messages = release.commits_since_last_tag("0.5.0")
        self.assertEqual(release.bump_level(messages), "minor")

    def test_manifest_and_latest_release_tag_skew_fails_closed(self) -> None:
        with mock.patch.object(release, "git", return_value="v0.4.0\nbenchmark"):
            with self.assertRaisesRegex(ValueError, "does not match"):
                release.release_baseline("0.5.0")

    def test_manifest_versions_must_be_equal_plain_semver(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "plugin.json"
            second = Path(directory) / "codex-plugin.json"
            first.write_text('{"version":"0.5.0"}', encoding="utf-8")
            second.write_text('{"version":"0.5.1"}', encoding="utf-8")
            with mock.patch.object(release, "MANIFESTS", (first, second)):
                with self.assertRaisesRegex(ValueError, "same plain semantic version"):
                    release.current_version()
            second.write_text('{"version":[]}', encoding="utf-8")
            with mock.patch.object(release, "MANIFESTS", (first, second)):
                with self.assertRaisesRegex(ValueError, "same plain semantic version"):
                    release.current_version()

    def test_repository_without_release_tags_uses_complete_history(self) -> None:
        with mock.patch.object(
            release,
            "git",
            side_effect=["benchmark\nv0.5.0-rc1", "feat: initial release\x00"],
        ) as git:
            messages = release.commits_since_last_tag("0.0.0")
        self.assertEqual(messages, ["feat: initial release"])
        self.assertEqual(git.call_args_list[-1], mock.call("log", "--format=%B%x00", "HEAD"))

    def test_breaking_footer_uses_full_message(self) -> None:
        message = "fix: keep old route\n\nMigration notes.\n\nBREAKING CHANGE: remove legacy field"
        self.assertEqual(release.bump_level([message]), "major")

    def test_scoped_conventional_headers(self) -> None:
        self.assertEqual(release.bump_level(["feat(router): add authority"]), "minor")
        self.assertEqual(release.bump_level(["fix(router)!: change precedence"]), "major")
        self.assertEqual(release.bump_level(["refactor(router)!: replace contract"]), "major")
        self.assertEqual(release.bump_level(["docs!: remove supported guide"]), "major")

    def test_both_breaking_footer_spellings_allow_multiline_details(self) -> None:
        self.assertEqual(release.bump_level(["chore: prepare\n\nBREAKING-CHANGE:\n migration details"]), "major")
        self.assertEqual(release.bump_level(["chore: prepare\n\nBREAKING CHANGE: incompatible"]), "major")

    def test_similar_words_do_not_trigger_major_or_minor(self) -> None:
        self.assertEqual(release.bump_level(["docs: discuss BREAKING CHANGE conventions"]), "patch")
        self.assertEqual(release.bump_level(["feature: prose only"]), "patch")

    def test_semantic_bumps(self) -> None:
        self.assertEqual(release.bumped("0.5.0", "patch"), "0.5.1")
        self.assertEqual(release.bumped("0.5.0", "minor"), "0.6.0")
        self.assertEqual(release.bumped("0.5.0", "major"), "1.0.0")


if __name__ == "__main__":
    unittest.main()
