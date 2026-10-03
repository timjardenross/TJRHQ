"""
Tests for the dependents/tests fact-gathering section in
core/engineering/context_enricher.py: for each file whose contents get
injected into a coding prompt, list who imports it and which tests cover it,
so a single-shot provider doesn't break callers it can't see.

Runs against a throwaway repo tree (ce._REPO_ROOT patched) — never the real
checkout.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.engineering import context_enricher as ce


def _write(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


class TestDependentsContext(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write(self.root, "core/eng/target_mod.py", "def f():\n    return 1\n")
        _write(self.root, "core/eng/sibling.py", "from . import target_mod\n")
        _write(self.root, "core/other/user.py", "from core.eng.target_mod import f\n")
        _write(self.root, "core/other/unrelated.py", "import json\n# target_mod mentioned in a comment\n")
        _write(self.root, "tests/test_target_mod.py", "from core.eng import target_mod\n")
        _write(self.root, "platform-runtime/loader.py", "X = 1\n")
        _write(self.root, "tools/uses_loader.py", "from loader import X\n")
        _write(self.root, "lcars-portal/src/lib/things.ts", "export const A = 1;\n")
        _write(self.root, "lcars-portal/src/app/page.tsx", "import { A } from '@/lib/things';\n")
        _write(self.root, "core/eng/node_modules/junk.py", "from core.eng.target_mod import f\n")
        self._patch = patch.object(ce, "_REPO_ROOT", self.root)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_python_absolute_relative_and_test_importers(self):
        out = ce._dependents_context(["core/eng/target_mod.py"])
        self.assertIn("core/eng/sibling.py:1:", out)
        self.assertIn("core/other/user.py:1:", out)
        self.assertIn("tests/test_target_mod.py:1:", out)
        self.assertIn("Tests that import it", out)

    def test_comment_mention_and_skipped_dirs_are_not_importers(self):
        out = ce._dependents_context(["core/eng/target_mod.py"])
        self.assertNotIn("unrelated.py", out)
        self.assertNotIn("node_modules", out)

    def test_platform_runtime_bare_import(self):
        out = ce._dependents_context(["platform-runtime/loader.py"])
        self.assertIn("tools/uses_loader.py:1:", out)
        self.assertIn("Tests: none found", out)

    def test_typescript_importer(self):
        out = ce._dependents_context(["lcars-portal/src/lib/things.ts"])
        self.assertIn("lcars-portal/src/app/page.tsx:1:", out)

    def test_non_code_targets_produce_no_section(self):
        _write(self.root, "core/eng/README.md", "# docs\n")
        self.assertEqual(ce._dependents_context(["core/eng/README.md"]), "")

    def test_scan_failure_degrades_to_empty(self):
        with patch.object(ce, "_find_dependents", side_effect=RuntimeError("boom")):
            self.assertEqual(ce._dependents_context(["core/eng/target_mod.py"]), "")

    def test_relative_import_from_other_package_does_not_match(self):
        _write(self.root, "core/other/rel.py", "from . import target_mod\n")
        out = ce._dependents_context(["core/eng/target_mod.py"])
        self.assertNotIn("core/other/rel.py", out)


if __name__ == "__main__":
    unittest.main()
