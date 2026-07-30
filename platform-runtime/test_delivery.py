"""Tests for the EDO delivery engine (MSN-EDO-001 → EDO-002/004/008).

Covers: lifecycle mapping + transition validation + hygiene normalisation;
bottleneck detection; metrics roll-up; reuse-first check; mission lint; and the
/delivery command routing. Pure/offline — Supabase access is mocked.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from lib.delivery import lifecycle, analysis  # noqa: E402
import commands.delivery as dlv  # noqa: E402


def _row(title, status, age, **kw):
    r = {"title": title, "status": status, "age_days": age,
         "delivery_state": lifecycle.canonical_state(status)}
    r.update(kw)
    return r


ROWS = [
    _row("Stuck design", "Designed", 9),
    _row("Fresh design", "Designed", 1),
    _row("Building", "Implemented", 8, branch_name="feat/x"),
    _row("In review no PR", "Tested", 3),
    _row("Validated waiting", "Validated", 4),
    _row("Blocked thing", "Blocked", 6),
    _row("Done", "Closed", 0, cycle_days=2.0, pr_url="http://pr/1", outcome_rating=4),
]


# ── lifecycle ─────────────────────────────────────────────────────────────────

class TestLifecycle(unittest.TestCase):
    def test_canonical_state_mapping(self):
        self.assertEqual(lifecycle.canonical_state("Designed"), "planned")
        self.assertEqual(lifecycle.canonical_state("Awaiting Number One Review"), "in_review")
        self.assertEqual(lifecycle.canonical_state("Closed"), "closed")
        self.assertEqual(lifecycle.canonical_state(None), "other")

    def test_is_open(self):
        self.assertTrue(lifecycle.is_open("Designed"))
        self.assertFalse(lifecycle.is_open("Closed"))

    def test_valid_transition(self):
        self.assertTrue(lifecycle.validate_transition("planned", "in_progress")[0])
        self.assertTrue(lifecycle.validate_transition(None, "planned")[0])

    def test_invalid_transition(self):
        self.assertFalse(lifecycle.validate_transition("planned", "closed")[0])
        self.assertFalse(lifecycle.validate_transition(None, "validated")[0])
        self.assertFalse(lifecycle.validate_transition("planned", "bogus")[0])

    def test_blocked_can_return_anywhere(self):
        self.assertTrue(lifecycle.validate_transition("blocked", "in_progress")[0])

    def test_normalisers(self):
        self.assertEqual(lifecycle.normalize_task_type("Engineering"), "engineering")
        self.assertEqual(lifecycle.normalize_priority("P1"), "p1")
        self.assertEqual(lifecycle.normalize_priority("urgent"), "unset")


# ── bottlenecks ───────────────────────────────────────────────────────────────

class TestBottlenecks(unittest.TestCase):
    def test_blocked_is_critical_and_first(self):
        f = analysis.detect_bottlenecks(ROWS)
        self.assertEqual(f[0].severity, "critical")
        self.assertTrue(any(x.kind == "blocked" for x in f))

    def test_stuck_planned_detected(self):
        f = analysis.detect_bottlenecks(ROWS)
        self.assertTrue(any(x.kind == "stuck_planned" and "Stuck design" in x.title for x in f))

    def test_fresh_design_not_flagged(self):
        f = analysis.detect_bottlenecks(ROWS)
        self.assertFalse(any("Fresh design" in x.title for x in f))

    def test_review_without_pr_flagged(self):
        f = analysis.detect_bottlenecks(ROWS)
        self.assertTrue(any(x.kind == "review_no_pr" for x in f))

    def test_closed_not_flagged(self):
        f = analysis.detect_bottlenecks(ROWS)
        self.assertFalse(any("Done" in x.title for x in f))


# ── metrics ───────────────────────────────────────────────────────────────────

class TestMetrics(unittest.TestCase):
    def test_counts(self):
        m = analysis.summarize_metrics(ROWS)
        self.assertEqual(m["total"], 7)
        self.assertEqual(m["closed"], 1)
        self.assertEqual(m["open"], 6)

    def test_rates_and_cycle(self):
        m = analysis.summarize_metrics(ROWS)
        self.assertAlmostEqual(m["pr_rate"], round(1 / 7, 2))
        self.assertEqual(m["avg_cycle_days"], 2.0)
        self.assertEqual(m["oldest_open_age_days"], 9)


# ── reuse ─────────────────────────────────────────────────────────────────────

class TestReuse(unittest.TestCase):
    def test_finds_capability_overlap(self):
        caps = [{"name": "Medical Bay Dashboard", "purpose": "recovery dashboard"}]
        miss = [{"title": "Build wellness widget", "description": "", "status": "Closed"}]
        out = analysis.reuse_check("improve the medical bay dashboard", caps, miss)
        self.assertTrue(out)
        self.assertEqual(out[0]["kind"], "capability")

    def test_no_overlap_empty(self):
        out = analysis.reuse_check("quantum warp core", [], [])
        self.assertEqual(out, [])


# ── lint ──────────────────────────────────────────────────────────────────────

class TestLint(unittest.TestCase):
    def test_task_type_case_flagged(self):
        rows = [_row("x", "Designed", 1, task_type="Engineering", priority="P1")]
        out = analysis.lint(rows)
        self.assertTrue(any(f.kind == "task_type_case" for f in out))

    def test_missing_priority_flagged(self):
        rows = [_row("x", "Designed", 1, task_type="engineering")]
        out = analysis.lint(rows)
        self.assertTrue(any(f.kind == "missing_priority" for f in out))

    def test_in_progress_missing_branch(self):
        rows = [_row("x", "Implemented", 1, task_type="engineering", priority="p1")]
        out = analysis.lint(rows)
        self.assertTrue(any(f.kind == "missing_branch" for f in out))


# ── command ───────────────────────────────────────────────────────────────────

class TestCommand(unittest.TestCase):
    def setUp(self):
        self._rows = patch.object(dlv.data, "fetch_delivery_rows", return_value=ROWS)
        self._rows.start()
        self._caps = patch.object(dlv.data, "fetch_capabilities", return_value=[])
        self._caps.start()

    def tearDown(self):
        self._rows.stop(); self._caps.stop()

    def test_help(self):
        self.assertIn("Engineering & Delivery Officer", dlv.handle_delivery(""))

    def test_status(self):
        out = dlv.handle_delivery("status")
        self.assertIn("Delivery status", out)
        self.assertIn("Stuck design", out)

    def test_bottlenecks(self):
        out = dlv.handle_delivery("bottlenecks")
        self.assertIn("bottlenecks", out.lower())
        self.assertIn("Blocked thing", out)

    def test_metrics(self):
        out = dlv.handle_delivery("metrics")
        self.assertIn("Delivery metrics", out)

    def test_lint(self):
        out = dlv.handle_delivery("lint")
        self.assertTrue("lint" in out.lower())

    def test_reuse_usage(self):
        self.assertIn("Usage", dlv.handle_delivery("reuse"))

    def test_reuse_query(self):
        out = dlv.handle_delivery("reuse medical bay dashboard")
        self.assertIn("Reuse", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
