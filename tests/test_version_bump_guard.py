"""
Regression tests for the version-bump guard (core/engineering/version_bump_guard.py)
and its wiring into batch_coding._open_files_pr / _maybe_open_pr.

Each "reproduces PR #nnn" test mirrors a real auto-dispatched PR from
2026-10-28 that claimed to bump a dependency but did not (see the guard's
module docstring). They must fail against the old behaviour (version-bump
title => existing-file guard off, model output unchecked) and pass now.

Never touches real GitHub/Mistral — github_pr and the env are mocked.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.engineering import batch_coding
from core.engineering import version_bump_guard as guard

BUMP = {"__mission_title__": "tailwindcss 3.4.13 -> 4.3.3 (npm release)"}

NPM_PKG = (
    '{\n'
    '  "name": "lcars-portal",\n'
    '  "dependencies": {\n'
    '    "@radix-ui/react-collapsible": "1.1.3",\n'
    '    "@radix-ui/react-collapse": "1.1.3",\n'
    '    "react": "18.3.1"\n'
    '  },\n'
    '  "devDependencies": {\n'
    '    "tailwindcss": "3.4.13"\n'
    '  }\n'
    '}\n'
)
PY_REQ = (
    "fastapi==0.110.0\n"
    "pydantic==2.13.4\n"
    "pydantic_core==2.46.4\n"
    "Weasyprint==69.0\n"
)


def _reader(mapping):
    return lambda rel: mapping.get(rel)


class TestParseTitle(unittest.TestCase):
    def test_parses_dependency_release_title(self):
        spec = guard.parse_title("@radix-ui/react-collapsible 1.1.3 -> 1.1.20 (npm release)")
        self.assertEqual((spec.name, spec.old, spec.new, spec.ecosystem),
                         ("@radix-ui/react-collapsible", "1.1.3", "1.1.20", "npm"))

    def test_rejects_other_titles_and_same_version(self):
        self.assertIsNone(guard.parse_title("Add voice service"))
        self.assertIsNone(guard.parse_title("pydantic 2.13.4 -> 2.13.4 (pypi release)"))


class TestAcceptsRealBumps(unittest.TestCase):
    def test_npm_exact_pin(self):
        new = NPM_PKG.replace('"@radix-ui/react-collapsible": "1.1.3"',
                              '"@radix-ui/react-collapsible": "1.1.20"')
        acc, rej = guard.filter_version_bump_files(
            "@radix-ui/react-collapsible 1.1.3 -> 1.1.20 (npm release)",
            {"lcars-portal/package.json": new}, _reader({"lcars-portal/package.json": NPM_PKG}))
        self.assertEqual(list(acc), ["lcars-portal/package.json"])
        self.assertEqual(rej, {})

    def test_npm_caret_range_preserved(self):
        old = NPM_PKG.replace('"3.4.13"', '"^3.4.13"')
        new = old.replace("^3.4.13", "^4.3.3")
        acc, rej = guard.filter_version_bump_files(
            "tailwindcss 3.4.13 -> 4.3.3 (npm release)",
            {"lcars-portal/package.json": new}, _reader({"lcars-portal/package.json": old}))
        self.assertEqual((len(acc), rej), (1, {}))

    def test_pypi_pin_with_case_and_separator_normalisation(self):
        new = PY_REQ.replace("Weasyprint==69.0", "Weasyprint==70.0")
        acc, rej = guard.filter_version_bump_files(
            "weasyprint 69.0 -> 70.0 (pypi release)",
            {"services/x/requirements.txt": new}, _reader({"services/x/requirements.txt": PY_REQ}))
        self.assertEqual((len(acc), rej), (1, {}))

    def test_pydantic_bump_does_not_swallow_pydantic_core_line(self):
        # Only the pydantic line may move; touching pydantic_core must be rejected.
        both = PY_REQ.replace("pydantic==2.13.4", "pydantic==2.13.5") \
                     .replace("pydantic_core==2.46.4", "pydantic_core==2.13.5")
        acc, rej = guard.filter_version_bump_files(
            "pydantic 2.13.4 -> 2.13.5 (pypi release)",
            {"platform-runtime/requirements.txt": both},
            _reader({"platform-runtime/requirements.txt": PY_REQ}))
        self.assertEqual(acc, {})
        self.assertIn("platform-runtime/requirements.txt", rej)


class TestRejectsTheSixObservedFailures(unittest.TestCase):
    def test_pr_462_463_new_unrelated_file(self):
        acc, rej = guard.filter_version_bump_files(
            "pydantic_core 2.46.4 -> 2.49.0 (pypi release)",
            {"core/health/capacity_score.py": "SCORE = 1\n"}, _reader({}))
        self.assertEqual(acc, {})
        self.assertIn("new file", rej["core/health/capacity_score.py"])

    def test_pr_462_465_file_identical_to_main(self):
        content = "def f():\n    return 1\n"
        acc, rej = guard.filter_version_bump_files(
            "weasyprint 69.0 -> 70.0 (pypi release)",
            {"core/engineering/batch_coding.py": content},
            _reader({"core/engineering/batch_coding.py": content}))
        self.assertEqual(acc, {})
        self.assertIn("not a pypi dependency manifest", rej["core/engineering/batch_coding.py"])

    def test_identical_manifest_is_a_noop(self):
        acc, rej = guard.filter_version_bump_files(
            "weasyprint 69.0 -> 70.0 (pypi release)",
            {"r/requirements.txt": PY_REQ}, _reader({"r/requirements.txt": PY_REQ}))
        self.assertEqual(acc, {})
        self.assertIn("identical", rej["r/requirements.txt"])

    def test_pr_464_markdown_note(self):
        acc, rej = guard.filter_version_bump_files(
            "@radix-ui/react-collapsible 1.1.3 -> 1.1.20 (npm release)",
            {"platform-runtime/dependencies/react-collapsible.md": "# note\n"}, _reader({}))
        self.assertEqual(acc, {})
        self.assertTrue(rej)

    def test_pr_467_patch_file_with_placeholder(self):
        patch_text = '--- a/package.json\n+++ b/package.json\n-  "tailwindcss": "^<DATE_TIME>",\n'
        acc, rej = guard.filter_version_bump_files(
            "tailwindcss 3.4.13 -> 4.3.3 (npm release)",
            {"platform-runtime/dependency_updates/tailwindcss_4.3.3.patch": patch_text}, _reader({}))
        self.assertEqual(acc, {})
        self.assertTrue(rej)

    def test_pr_466_root_package_json_overwrite(self):
        old = (
            '{\n  "name": "starship-endeavour",\n  "version": "1.0.0",\n  "private": true,\n'
            '  "scripts": {\n    "adr:build": "log4brains build"\n  },\n'
            '  "devDependencies": {\n    "log4brains": "^1.1.0"\n  }\n}\n'
        )
        new = (
            '{\n  "name": "your-project-name",\n  "version": "1.0.0",\n'
            '  "dependencies": {\n    "tailwindcss": "4.3.3"\n  },\n'
            '  "devDependencies": {},\n  "license": "ISC"\n}\n'
        )
        acc, rej = guard.filter_version_bump_files(
            "tailwindcss 3.4.13 -> 4.3.3 (npm release)",
            {"package.json": new}, _reader({"package.json": old}))
        self.assertEqual(acc, {})
        self.assertIn("package.json", rej)

    def test_extra_unrelated_line_change_is_rejected(self):
        new = NPM_PKG.replace('"tailwindcss": "3.4.13"', '"tailwindcss": "4.3.3"') \
                     .replace('"react": "18.3.1"', '"react": "19.0.0"')
        acc, rej = guard.filter_version_bump_files(
            "tailwindcss 3.4.13 -> 4.3.3 (npm release)",
            {"lcars-portal/package.json": new}, _reader({"lcars-portal/package.json": NPM_PKG}))
        self.assertEqual(acc, {})
        self.assertIn("does not name tailwindcss", rej["lcars-portal/package.json"])

    def test_added_line_is_rejected(self):
        new = NPM_PKG.replace('"tailwindcss": "3.4.13"', '"tailwindcss": "4.3.3",\n    "extra": "1"')
        acc, rej = guard.filter_version_bump_files(
            "tailwindcss 3.4.13 -> 4.3.3 (npm release)",
            {"lcars-portal/package.json": new}, _reader({"lcars-portal/package.json": NPM_PKG}))
        self.assertEqual(acc, {})
        self.assertIn("line count", rej["lcars-portal/package.json"])

    def test_lockfile_is_not_accepted(self):
        acc, rej = guard.filter_version_bump_files(
            "tailwindcss 3.4.13 -> 4.3.3 (npm release)",
            {"lcars-portal/package-lock.json": '"tailwindcss": "4.3.3"\n'},
            _reader({"lcars-portal/package-lock.json": '"tailwindcss": "3.4.13"\n'}))
        self.assertEqual(acc, {})
        self.assertIn("not a npm dependency manifest", rej["lcars-portal/package-lock.json"])

    def test_non_bump_title_rejects_everything(self):
        acc, rej = guard.filter_version_bump_files("Add voice", {"a.py": "x\n"}, _reader({"a.py": "y\n"}))
        self.assertEqual(acc, {})
        self.assertTrue(rej)


class TestWiredIntoBatchCoding(unittest.TestCase):
    def _env(self):
        return patch.object(batch_coding, "_env_value", side_effect=lambda k: {
            "GITHUB_TOKEN": "test-token", "GITHUB_REPO": "example/repo",
        }.get(k, ""))

    def test_bad_bump_never_reaches_github(self):
        with self._env(), patch.object(batch_coding.github_pr, "open_files_pr") as mock_open:
            res = batch_coding._open_files_pr(
                "ENG-HANDOFF-T", {"platform-runtime/dependency_updates/x.patch": "junk\n"}, BUMP)
        mock_open.assert_not_called()
        self.assertFalse(res["opened"])
        self.assertEqual(res["reason"], "version_bump_guard_rejected")

    def test_good_bump_opens_pr_with_only_the_accepted_file(self):
        real = REPO_ROOT / "lcars-portal" / "package.json"
        old = real.read_text(encoding="utf-8")
        self.assertIn('"tailwindcss": "3.4.13"', old)
        new = old.replace('"tailwindcss": "3.4.13"', '"tailwindcss": "4.3.3"')
        files = {"lcars-portal/package.json": new, "junk/extra.py": "x = 1\n"}
        with self._env(), patch.object(
            batch_coding.github_pr, "open_files_pr", return_value={"opened": True, "url": "u", "branch": "b"},
        ) as mock_open, patch.object(batch_coding, "_run_xo_review_and_notify"):
            res = batch_coding._open_files_pr("ENG-HANDOFF-T", files, BUMP)
        self.assertTrue(res["opened"])
        sent = mock_open.call_args.args[1]
        self.assertEqual(list(sent), ["lcars-portal/package.json"])
        self.assertIn("junk/extra.py", mock_open.call_args.kwargs["body"])

    def test_non_bump_title_unaffected_by_guard(self):
        with self._env(), patch.object(
            batch_coding.github_pr, "open_files_pr", return_value={"opened": True, "url": "u", "branch": "b"},
        ) as mock_open:
            batch_coding._open_files_pr("ENG-HANDOFF-T", {"new_module.py": "x = 1\n"},
                                        {"__mission_title__": "Add a module"})
        self.assertEqual(list(mock_open.call_args.args[1]), ["new_module.py"])

    def test_diff_mode_never_opens_pr_for_bump_title(self):
        diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -0,0 +1 @@\n+x = 1\n"
        with self._env(), patch.object(batch_coding.github_pr, "open_draft_pr") as mock_open:
            res = batch_coding._maybe_open_pr("ENG-HANDOFF-T", diff, BUMP)
        mock_open.assert_not_called()
        self.assertEqual(res, {})


if __name__ == "__main__":
    unittest.main()
