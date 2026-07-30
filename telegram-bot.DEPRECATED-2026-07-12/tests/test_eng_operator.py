"""Offline unit tests for the Directed Engineering Operator (eng_operator).

Hermetic: module-level paths are redirected to a temp sandbox so tests never
write into the real repo, and the GLM call is injected (no network).
"""

import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))  # telegram-bot/ on path

import eng_operator as eo  # noqa: E402
from core.coordination.engineering_handoff_reader import EngineeringStatus  # noqa: E402

MISSION = "USS-TJR-MSN-9999"


def _fake_glm(prompt, system=None):
    # assert the persona is always attached (containment requirement)
    assert system and "Engineering Officer" in system
    return f"FAKE-OUTPUT for prompt-len={len(prompt)}", "glm-5.2-test"


class EngOperatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        # redirect every write/read path into the sandbox
        self._saved = {k: getattr(eo, k) for k in
                       ("MISSIONS_DIR", "ACTIVE_DIR", "COMPLETED_DIR", "HANDOFFS_DIR",
                        "ARTIFACTS_DIR", "ENG_STATUS_DIR", "REGISTRY_FILE",
                        "DECISION_REGISTER", "LESSONS_FILE")}
        eo.MISSIONS_DIR = root / "Missions"
        eo.ACTIVE_DIR = eo.MISSIONS_DIR / "Active"
        eo.COMPLETED_DIR = eo.MISSIONS_DIR / "Completed"
        eo.HANDOFFS_DIR = eo.MISSIONS_DIR / "Engineering-Handoffs"
        eo.ARTIFACTS_DIR = eo.HANDOFFS_DIR / "artifacts"
        eo.ENG_STATUS_DIR = eo.MISSIONS_DIR / "Engineering-Status"
        eo.REGISTRY_FILE = root / "mission-index.txt"
        eo.DECISION_REGISTER = root / "decision-register.txt"
        eo.LESSONS_FILE = root / "lessons.md"
        eo.ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
        eo.REGISTRY_FILE.write_text(
            "| Mission ID | Title | Priority | Status | Owner | Specialist | Ref |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            f"| {MISSION} | Test Mission | P2 Medium | ACTIVE | Chief Eng | Chief Eng | n/a |\n",
            encoding="utf-8",
        )
        (eo.ACTIVE_DIR / f"{MISSION}-Test.md").write_text(
            f"# {MISSION} — Test Mission\n\n**Status:** ACTIVE\n**Priority:** P2\n\n"
            "## Mission Statement\nDo the test thing.\n", encoding="utf-8")

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(eo, k, v)
        self.tmp.cleanup()

    # --- status normalisation ---
    def test_normalise_status_variants(self):
        self.assertEqual(eo.normalise_status("In Progress"), EngineeringStatus.IN_PROGRESS)
        self.assertEqual(eo.normalise_status("in_progress"), EngineeringStatus.IN_PROGRESS)
        self.assertEqual(eo.normalise_status("awaiting-review"), EngineeringStatus.AWAITING_REVIEW)
        self.assertEqual(eo.normalise_status("COMPLETED"), EngineeringStatus.COMPLETED)
        self.assertIsNone(eo.normalise_status("Deployed"))

    # --- mission existence / refusal ---
    def test_mission_exists_and_unknown(self):
        self.assertTrue(eo.mission_exists(MISSION))
        self.assertFalse(eo.mission_exists("USS-TJR-MSN-0000"))
        self.assertIn("can't find mission", eo.cmd_pickup("USS-TJR-MSN-0000"))

    # --- status: stage + approve writes ledger; invalid refused ---
    def test_status_invalid_refused(self):
        summary, action = eo.stage_status(MISSION, "Deployed", "tg:1")
        self.assertIsNone(action)
        self.assertIn("Invalid status", summary)

    def test_status_stage_then_apply_records(self):
        summary, action = eo.stage_status(MISSION, "In Progress", "tg:1")
        self.assertIsNotNone(action)
        self.assertEqual(action.kind, "status")
        self.assertIsNone(eo.current_engineering_status(MISSION))  # nothing written yet
        result = eo.apply_action(action)
        self.assertIn("In Progress", result)
        self.assertEqual(eo.current_engineering_status(MISSION), EngineeringStatus.IN_PROGRESS)
        # ledger file exists and contains the transition
        led = eo._ledger_path(MISSION)
        self.assertTrue(led.exists())
        self.assertIn("STATUS:", led.read_text())

    # --- log: stage + apply appends ---
    def test_log_stage_then_apply(self):
        summary, action = eo.stage_log(MISSION, "did the thing", "tg:1")
        self.assertEqual(action.kind, "log")
        eo.apply_action(action)
        self.assertIn("did the thing", eo._ledger_path(MISSION).read_text())

    def test_log_empty_refused(self):
        _, action = eo.stage_log(MISSION, "   ", "tg:1")
        self.assertIsNone(action)

    # --- handoff write ---
    def test_handoff_apply_writes_file(self):
        _, action = eo.stage_handoff(MISSION, "tg:1")
        result = eo.apply_action(action)
        self.assertIn("Handoff written", result)
        files = list(eo.HANDOFFS_DIR.glob("ENG-HANDOFF-*.md"))
        self.assertEqual(len(files), 1)
        body = files[0].read_text()
        self.assertIn("APPROVED_FOR_ENGINEERING", body)
        self.assertIn(f"Mission ID: {MISSION}", body)
        self.assertIn("Batch Status: PENDING", body)

    # --- patch: generate (injected GLM) then approve writes review-only artifact ---
    def test_patch_stage_and_apply_artifact(self):
        summary, action = eo.stage_patch(MISSION, "tg:1", glm_call=_fake_glm)
        self.assertEqual(action.kind, "patch")
        self.assertIn("REVIEW ONLY", summary)
        result = eo.apply_action(action)
        self.assertIn("review-only patch artifact", result.lower())
        arts = list(eo.ARTIFACTS_DIR.glob("*.patch.md"))
        self.assertEqual(len(arts), 1)
        self.assertIn("do not apply blindly", arts[0].read_text().lower())

    # --- plan/review run through build_prompt + injected GLM, with footer ---
    def test_plan_uses_glm_and_has_footer(self):
        out = eo.cmd_plan(MISSION, glm_call=_fake_glm)
        self.assertIn("FAKE-OUTPUT", out)
        self.assertIn("Evidence:", out)
        self.assertIn("Next recommended action:", out)

    def test_review_unknown_refused(self):
        self.assertIn("can't find mission", eo.cmd_review("USS-TJR-MSN-0000", glm_call=_fake_glm))

    # --- pending store ---
    def test_pending_store(self):
        store = eo.PendingStore()
        a = eo.PendingAction("log", MISSION, "x")
        store.stage(7, a)
        self.assertIs(store.peek(7), a)
        self.assertIs(store.take(7), a)
        self.assertIsNone(store.take(7))

    # --- missions listing includes the active mission ---
    def test_missions_listing(self):
        out = eo.cmd_missions()
        self.assertIn(MISSION, out)
        self.assertIn("Evidence:", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
