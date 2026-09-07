"""
Tests for dashboard.py's /api/engineering-handoffs route (2026-09-06):
a Captain-facing engineering-queue page needed a real backend to read from,
and core/coordination/engineering_handoff_reader.py already computes
everything required (title, priority, live PR URL, lifecycle status) —
this route is pure HTTP surfacing, no new parsing logic of its own.

Never touches real Missions/Engineering-Handoffs/ or data/self-improvement/
— every test points engineering_handoff_reader.DEFAULT_HANDOFFS_DIR at a
scratch tmpdir and restores it in tearDown. Bare-sibling-import convention
matches the other scripts/self_improvement test files.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))
sys.path.insert(0, str(REPO_ROOT))

import dashboard  # noqa: E402
import core.coordination.engineering_handoff_reader as ehr  # noqa: E402


def write_handoff(handoffs_dir: Path, name: str, **overrides) -> Path:
    fields = {
        "Status": "APPROVED_FOR_ENGINEERING",
        "Batch Status": "DELIVERED",
    }
    fields.update(overrides)
    handoffs_dir.mkdir(parents=True, exist_ok=True)
    path = handoffs_dir / f"{name}.md"
    header = "\n".join(f"- {k}: {v}" for k, v in fields.items())
    path.write_text(f"{header}\n\n## Mission Title\n{name}\n", encoding="utf-8")
    return path


class TestEngineeringHandoffsApi(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.handoffs_dir = self.tmpdir / "Missions" / "Engineering-Handoffs"
        self._orig_dir = ehr.DEFAULT_HANDOFFS_DIR
        ehr.DEFAULT_HANDOFFS_DIR = self.handoffs_dir
        self.client = dashboard.app.test_client()

    def tearDown(self):
        ehr.DEFAULT_HANDOFFS_DIR = self._orig_dir
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_directory_returns_empty_list_not_an_error(self):
        res = self.client.get("/api/engineering-handoffs")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["handoffs"], [])

    def test_delivered_handoff_with_pr_url_surfaces_it(self):
        write_handoff(
            self.handoffs_dir, "ENG-HANDOFF-TEST-001",
            **{"PR URL": "https://github.com/timjardenross/TJRHQ/pull/999"},
        )
        res = self.client.get("/api/engineering-handoffs")
        self.assertEqual(res.status_code, 200)
        handoffs = res.get_json()["handoffs"]
        self.assertEqual(len(handoffs), 1)
        self.assertEqual(handoffs[0]["metadata"]["pr_url"],
                         "https://github.com/timjardenross/TJRHQ/pull/999")
        self.assertEqual(handoffs[0]["metadata"]["engineering_status"], "Awaiting Review")
        self.assertIn("https://github.com/timjardenross/TJRHQ/pull/999", handoffs[0]["next_action"])

    def test_completed_handoff_is_excluded_not_outstanding_work(self):
        write_handoff(self.handoffs_dir, "ENG-HANDOFF-TEST-002", **{"Batch Status": "MERGED"})
        res = self.client.get("/api/engineering-handoffs")
        self.assertEqual(res.get_json()["handoffs"], [])

    def test_unapproved_handoff_is_excluded(self):
        write_handoff(self.handoffs_dir, "ENG-HANDOFF-TEST-003", Status="Idea")
        res = self.client.get("/api/engineering-handoffs")
        self.assertEqual(res.get_json()["handoffs"], [])

    def test_reader_failure_degrades_to_empty_list_not_500(self):
        with patch.object(ehr, "load_engineering_handoffs", side_effect=RuntimeError("boom")):
            res = self.client.get("/api/engineering-handoffs")
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.get_json()["handoffs"], [])


if __name__ == "__main__":
    unittest.main()
