"""
Tests for dashboard.py's /api/engineering-handoffs/artifact route (2026-09-07):
the Engineering Handoffs page (PR #58) could only ever print a handoff's
review-artifact path as inert text — reading it required VM shell access,
which the Captain may not have. This route serves the artifact's content so
the portal can show it in place, with `path` locked to a file directly
inside Missions/Engineering-Handoffs/artifacts/ to rule out path traversal.

Never touches the real repo tree — every test points dashboard.REPO_ROOT at
a scratch tmpdir and restores it in tearDown. Bare-sibling-import convention
matches the other scripts/self_improvement test files.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))
sys.path.insert(0, str(REPO_ROOT))

import dashboard


class TestEngineeringHandoffArtifactApi(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.artifacts_dir = self.tmpdir / "Missions" / "Engineering-Handoffs" / "artifacts"
        self.artifacts_dir.mkdir(parents=True)
        self._orig_root = dashboard.REPO_ROOT
        dashboard.REPO_ROOT = self.tmpdir
        self.client = dashboard.app.test_client()

    def tearDown(self):
        dashboard.REPO_ROOT = self._orig_root
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _rel(self, filename: str) -> str:
        return str((self.artifacts_dir / filename).relative_to(self.tmpdir))

    def test_returns_the_artifact_content(self):
        (self.artifacts_dir / "ENG-HANDOFF-1.patch.md").write_text(
            "# Proposed code changes\n- Handoff: ENG-HANDOFF-1\n\n---\n\nsome diff text\n",
            encoding="utf-8",
        )
        res = self.client.get(f"/api/engineering-handoffs/artifact?path={self._rel('ENG-HANDOFF-1.patch.md')}")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertIn("some diff text", body["content"])

    def test_missing_path_param_is_a_400_not_a_crash(self):
        res = self.client.get("/api/engineering-handoffs/artifact")
        self.assertEqual(res.status_code, 400)

    def test_nonexistent_artifact_is_a_404(self):
        res = self.client.get(f"/api/engineering-handoffs/artifact?path={self._rel('does-not-exist.patch.md')}")
        self.assertEqual(res.status_code, 404)

    def test_path_traversal_outside_the_artifacts_dir_is_rejected(self):
        secret = self.tmpdir / "secret.md"
        secret.write_text("top secret", encoding="utf-8")
        res = self.client.get("/api/engineering-handoffs/artifact?path=Missions/Engineering-Handoffs/artifacts/../../../secret.md")
        self.assertEqual(res.status_code, 400)

    def test_subdirectory_of_the_artifacts_dir_is_rejected(self):
        nested = self.artifacts_dir / "nested"
        nested.mkdir()
        (nested / "sneaky.md").write_text("nope", encoding="utf-8")
        res = self.client.get(
            f"/api/engineering-handoffs/artifact?path={self._rel('nested/sneaky.md')}"
        )
        self.assertEqual(res.status_code, 400)

    def test_non_md_extension_is_rejected(self):
        (self.artifacts_dir / "ENG-HANDOFF-2.sh").write_text("echo hi", encoding="utf-8")
        res = self.client.get(f"/api/engineering-handoffs/artifact?path={self._rel('ENG-HANDOFF-2.sh')}")
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
