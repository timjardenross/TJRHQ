"""The shadow exporter is read-only, complete, minimal and offline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "scripts"))

import export_weekly_evidence as ex
import render_shadow_report as rs

START, END = "2026-11-16T13:00:00Z", "2026-11-23T13:00:00Z"


class FakeDB:
    """Serves paged PostgREST-style responses and records every request."""

    def __init__(self, events=2300):
        self.calls, self.events = [], events

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        rng = headers.get("Range", "")
        if headers.get("Prefer") == "count=exact":
            n = 2376 if "signal_status=eq.DUPLICATE" not in url and "geography" not in url else (46 if "DUPLICATE" in url else 564)
            return 206, {"Content-Range": f"0-0/{n}"}, b"[]"
        a, b = (int(x) for x in rng.split("-"))
        if "/intelligence_events?" in url:
            rows = [{"event_id": f"{i:08x}-0000", "raw_title": f"Event {i} outage", "raw_summary": "s" * 400,
                     "canonical_url": f"https://x/{i}", "collected_at": "2026-11-20T00:00:00Z", "geography": "AU",
                     "rank_score": 20, "operational_relevance": 0.5, "osint_confidence_level": "HIGH",
                     "disposition": "WATCH", "risk_rating": "LOW",
                     "intelligence_source_registry": {"source_name": "ABC News"}} for i in range(a, min(b + 1, self.events))]
        elif "/health_signals?" in url:
            rows = [{"title": "Trial A", "health_source_registry": {"source_name": "ClinicalTrials.gov"}}] * 3 + \
                   [{"title": "Journal paper B", "health_source_registry": {"source_name": "The Lancet"}}]
            rows = rows[a:b + 1]
        elif "/capacity_checkins?" in url:
            rows = [{"log_date": "2026-11-03"}, {"log_date": "2026-11-04"}][a:b + 1]
        else:
            rows = []
        return 200, {}, json.dumps(rows).encode()


def _export(events=2300):
    db = FakeDB(events)
    return db, ex.export(ex.Reader("https://example.supabase.co", "k", http=db), START, END)


class TestReadOnlyAndOffline:
    def test_only_get_requests_are_made(self):
        db, _ = _export()
        assert db.calls
        src = (_REPO / "scripts" / "export_weekly_evidence.py").read_text()
        assert 'method="GET"' in src
        for banned in ('"POST"', '"PUT"', '"PATCH"', '"DELETE"', "/rpc/", "urlopen(req, data"):
            assert banned not in src

    def test_no_messaging_scheduler_or_delivery_code(self):
        src = (_REPO / "scripts" / "export_weekly_evidence.py").read_text().lower()
        for banned in ("telegram", "smtp", "resend", "send_email", "notify", "apscheduler", "subprocess", "socket"):
            assert banned not in src

    def test_missing_credentials_exports_nothing(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        out = tmp_path / "o.json"
        assert ex.main(["--start", START, "--end", END, "--out", str(out)]) == 2
        assert not out.exists()


class TestCompletenessAndMinimisation:
    def test_full_week_is_paged_not_truncated(self):
        db, data = _export(events=2300)
        assert len(data["events"]) == 2300 and data["universe"]["exported_events"] == 2300
        ranges = [h["Range"] for u, h in db.calls if "/intelligence_events?" in u and "Range" in h and h.get("Prefer") != "count=exact"]
        assert ranges[:3] == ["0-999", "1000-1999", "2000-2999"]

    def test_exact_counts_come_from_content_range(self):
        _, data = _export()
        assert data["universe"] == {"usable": 2376, "duplicates": 46, "au_events": 564, "exported_events": 2300}

    def test_window_and_suppression_filters_applied(self):
        db, _ = _export()
        q = next(u for u, _h in db.calls if "/intelligence_events?" in u)
        assert "collected_at=gte.2026-11-16T13:00:00Z" in q and "collected_at=lt.2026-11-23T13:00:00Z" in q
        assert "suppressed=eq.false" in q and "GitHub" in q

    def test_capacity_is_dates_only_never_values(self):
        db, data = _export()
        assert data["capacity"]["entries"] == [{"log_date": "2026-11-03"}, {"log_date": "2026-11-04"}]
        selects = [u for u, _h in db.calls if "/capacity_checkins?" in u or "/recovery_pulses?" in u or "/captains_log_entries?" in u]
        for u in selects:
            assert "capacity_state" not in u and "pain" not in u and "energy" not in u and "sleep" not in u

    def test_summary_is_truncated_and_ids_shortened(self):
        _, data = _export(5)
        assert all(len(e["summary"]) <= 300 and len(e["id"]) == 8 for e in data["events"])

    def test_health_split_and_leads(self):
        _, data = _export(1)
        assert data["health"]["registrations"] == 3 and data["health"]["other"] == 1
        assert data["health"]["leads"] == ["Journal paper B"]


class TestFeedsTheShadowRenderer:
    def test_export_renders_a_brief_with_the_real_universe(self):
        _, data = _export(120)
        text = rs.render(data, "test week")
        assert text.startswith("SHADOW OUTPUT") and "2376 usable events" in text
        assert "120 assessed (a candidate pool, not the full week)" in text
