"""
Tests for scripts/self_improvement/bulk_decide.py.

Runs the real script code against a throwaway local HTTP server that mimics
the three dashboard endpoints it uses (GET /api/opportunity/<id>,
GET /api/opportunities, POST /api/opportunity/decide). Never touches the
real dashboard or opportunity store.
"""

import io
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.self_improvement import bulk_decide as bd


class _FakeDashboard(BaseHTTPRequestHandler):
    store: ClassVar[dict] = {}
    decisions: ClassVar[list] = []
    fail_decide_for: ClassVar[set] = set()

    def log_message(self, *args):  # silence
        pass

    def _send(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/opportunities":
            states = set(parse_qs(url.query).get("state", [""])[0].split(","))
            opps = [o for o in self.store.values() if o["lifecycle_state"] in states]
            return self._send(200, {"opportunities": opps, "total": len(opps)})
        if url.path.startswith("/api/opportunity/"):
            opp = self.store.get(url.path.rsplit("/", 1)[1])
            return self._send(200, opp) if opp else self._send(404, {"error": "Opportunity not found"})
        self._send(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if body["opportunity_id"] in self.fail_decide_for:
            return self._send(500, {"error": "Failed to update opportunity"})
        self.decisions.append(body)
        self.store[body["opportunity_id"]]["lifecycle_state"] = "rejected"
        self._send(200, {"success": True})


class BulkDecideTest(unittest.TestCase):
    def setUp(self):
        _FakeDashboard.store = {
            "EVO-0001": {"opportunity_id": "EVO-0001", "title": "postcss 8.5.28 -> 8.5.31 (npm release)",
                         "lifecycle_state": "proposed", "mission_id": None},
            "EVO-0002": {"opportunity_id": "EVO-0002", "title": "knip 5.88.1 -> 6.38.0 (npm release)",
                         "lifecycle_state": "verifying", "mission_id": "USS-TJR-MSN-1"},
            "EVO-0003": {"opportunity_id": "EVO-0003", "title": "pylint 2.17.0 -> 4.1.2 (pypi release)",
                         "lifecycle_state": "rejected", "mission_id": None},
            "EVO-0004": {"opportunity_id": "EVO-0004", "title": "something unrelated",
                         "lifecycle_state": "proposed", "mission_id": None},
        }
        _FakeDashboard.decisions = []
        _FakeDashboard.fail_decide_for = set()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeDashboard)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _items(self):
        return [
            bd.Item("EVO-0001", "postcss", "done in #457"),
            bd.Item("EVO-0002", "knip", "deferred"),
            bd.Item("EVO-0003", "pylint", "deferred"),       # already rejected -> skip
            bd.Item("EVO-0004", "postcss", "wrong title"),   # title mismatch -> skip
            bd.Item("EVO-9999", "anything", "missing"),      # 404 -> skip
        ]

    def test_dry_run_writes_nothing(self):
        out = io.StringIO()
        rc = bd.run(self.base, self._items(), apply=False, out=out)
        self.assertEqual(rc, 0)
        self.assertEqual(_FakeDashboard.decisions, [])
        text = out.getvalue()
        self.assertIn("WOULD   EVO-0001", text)
        self.assertIn("WOULD   EVO-0002", text)
        self.assertIn("dry run", text)

    def test_apply_rejects_only_matching_open_items_with_tagged_reason(self):
        out = io.StringIO()
        rc = bd.run(self.base, self._items(), apply=True, out=out)
        self.assertEqual(rc, 0)
        sent = {d["opportunity_id"]: d for d in _FakeDashboard.decisions}
        self.assertEqual(set(sent), {"EVO-0001", "EVO-0002"})
        for d in sent.values():
            self.assertEqual(d["decision_type"], "reject")
            self.assertTrue(d["reasoning"].startswith(bd.BATCH_TAG))
        self.assertIn("done in #457", sent["EVO-0001"]["reasoning"])
        text = out.getvalue()
        self.assertIn("SKIP    EVO-0003  already rejected", text)
        self.assertIn("title mismatch", text)
        self.assertIn("SKIP    EVO-9999  not found", text)
        # the mismatched item must be untouched
        self.assertEqual(_FakeDashboard.store["EVO-0004"]["lifecycle_state"], "proposed")

    def test_works_against_the_simplified_lifecycle_api(self):
        # Simplified API: lifecycle_state is a stage, the fine state is stage_detail.
        _FakeDashboard.store = {
            "EVO-0001": {"opportunity_id": "EVO-0001", "title": "postcss 8.5.28 -> 8.5.31 (npm release)",
                         "lifecycle_state": "to_decide", "stage_detail": "proposed"},
            "EVO-0002": {"opportunity_id": "EVO-0002", "title": "knip 5.88.1 -> 6.38.0 (npm release)",
                         "lifecycle_state": "in_progress", "stage_detail": "verifying"},
            "EVO-0003": {"opportunity_id": "EVO-0003", "title": "pylint 2.17.0 -> 4.1.2 (pypi release)",
                         "lifecycle_state": "closed", "stage_detail": "rejected"},
        }
        out = io.StringIO()
        rc = bd.run(self.base, self._items()[:3], apply=True, out=out)
        self.assertEqual(rc, 0)
        self.assertEqual({d["opportunity_id"] for d in _FakeDashboard.decisions}, {"EVO-0001", "EVO-0002"})
        self.assertIn("SKIP    EVO-0003  already rejected", out.getvalue())

    def test_second_apply_is_idempotent(self):
        bd.run(self.base, self._items(), apply=True, out=io.StringIO())
        _FakeDashboard.decisions.clear()
        rc = bd.run(self.base, self._items(), apply=True, out=io.StringIO())
        self.assertEqual(rc, 0)
        self.assertEqual(_FakeDashboard.decisions, [])

    def test_server_error_is_reported_and_exit_nonzero_but_continues(self):
        _FakeDashboard.fail_decide_for = {"EVO-0001"}
        out = io.StringIO()
        rc = bd.run(self.base, self._items(), apply=True, out=out)
        self.assertEqual(rc, 1)
        self.assertIn("ERROR   EVO-0001", out.getvalue())
        self.assertEqual([d["opportunity_id"] for d in _FakeDashboard.decisions], ["EVO-0002"])

    def test_unreachable_dashboard_is_an_error_not_a_crash(self):
        out = io.StringIO()
        rc = bd.run("http://127.0.0.1:1", [bd.Item("EVO-0001", "postcss", "x")], apply=True, out=out)
        self.assertEqual(rc, 1)
        self.assertIn("cannot reach", out.getvalue())

    def test_list_shows_only_open_items(self):
        opps = bd.list_open(self.base)
        self.assertEqual({o["opportunity_id"] for o in opps}, {"EVO-0001", "EVO-0002", "EVO-0004"})

    def test_extra_file_items_are_loaded_and_validated(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.json"
            good.write_text(json.dumps([{"id": "EVO-0004", "title_contains": "unrelated", "reason": "r"}]))
            self.assertEqual(bd.load_extra(str(good)), [bd.Item("EVO-0004", "unrelated", "r")])
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps([{"id": "EVO-0004"}]))
            with self.assertRaises(SystemExit):
                bd.load_extra(str(bad))

    def test_builtin_items_are_unique_and_all_have_reasons(self):
        ids = [i.id for i in bd.BUILTIN_ITEMS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 14)
        self.assertTrue(all(i.reason.strip() and i.title_contains.strip() for i in bd.BUILTIN_ITEMS))


if __name__ == "__main__":
    unittest.main()
