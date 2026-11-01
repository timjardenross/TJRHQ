"""Write-time dedupe of identical memory metrics (Supabase DB-size review 2026-10-10)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.coordination import memory_metrics
from core.coordination.memory_metrics import log_memory_metric

_WRITE = "tools.supabase.client.log_memory_event"
_CLOCK = "core.coordination.memory_metrics.time.monotonic"


def _ok():
    return SimpleNamespace(ok=True)


def _fail():
    return SimpleNamespace(ok=False)


class MemoryMetricsDedupeTests(unittest.TestCase):
    def setUp(self):
        memory_metrics._recent_writes.clear()
        self.addCleanup(memory_metrics._recent_writes.clear)

    def _call(self, **overrides):
        kwargs = {
            "source": "number_one",
            "action": "mission_registry_context_used",
            "outcome": "success",
            "memory_type": "mission",
            "details": {"result_count": 3},
        }
        kwargs.update(overrides)
        return log_memory_metric(**kwargs)

    def test_identical_metric_inside_window_is_written_once(self):
        with patch(_WRITE, return_value=_ok()) as write, patch(_CLOCK, side_effect=[100.0, 130.0]):
            self.assertTrue(self._call())
            self.assertTrue(self._call())
        self.assertEqual(write.call_count, 1)

    def test_different_outcome_details_or_source_are_each_written(self):
        with patch(_WRITE, return_value=_ok()) as write:
            self._call()
            self._call(outcome="duplicate_warning")
            self._call(details={"result_count": 4})
            self._call(source="mission_registry")
        self.assertEqual(write.call_count, 4)

    def test_details_key_order_does_not_defeat_dedupe(self):
        with patch(_WRITE, return_value=_ok()) as write:
            self._call(details={"a": 1, "b": 2})
            self._call(details={"b": 2, "a": 1})
        self.assertEqual(write.call_count, 1)

    def test_written_again_after_window_expires(self):
        # clock reads: remember(1st write)=0, check(2nd call)=3601 (expired -> write), remember=3601
        with patch(_WRITE, return_value=_ok()) as write, patch(_CLOCK, side_effect=[0.0, 3601.0, 3601.0]):
            self._call()
            self._call()
        self.assertEqual(write.call_count, 2)

    def test_window_zero_disables_dedupe(self):
        with patch.dict("os.environ", {"MEMORY_METRICS_DEDUPE_SECONDS": "0"}), patch(_WRITE, return_value=_ok()) as write:
            self._call()
            self._call()
            self._call()
        self.assertEqual(write.call_count, 3)

    def test_failed_write_is_not_remembered_and_is_retried(self):
        with patch(_WRITE, side_effect=[_fail(), _ok()]) as write:
            self.assertFalse(self._call())
            self.assertTrue(self._call())
        self.assertEqual(write.call_count, 2)

    def test_write_exception_is_swallowed_and_not_remembered(self):
        with patch(_WRITE, side_effect=[RuntimeError("boom"), _ok()]) as write:
            self.assertFalse(self._call())
            self.assertTrue(self._call())
        self.assertEqual(write.call_count, 2)

    def test_key_table_stays_bounded(self):
        with patch(_WRITE, return_value=_ok()):
            for i in range(memory_metrics._DEDUPE_MAX_KEYS + 50):
                self._call(details={"i": i})
        self.assertLessEqual(len(memory_metrics._recent_writes), memory_metrics._DEDUPE_MAX_KEYS)


if __name__ == "__main__":
    unittest.main()
