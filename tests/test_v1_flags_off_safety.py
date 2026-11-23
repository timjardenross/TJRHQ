"""Release safety for the dormant V1 foundation: flags off by default, no reads/writes when off, failure leaves legacy briefs intact."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import brief_evidence as be
from intelligence import captains_brief as cb

ALL = (be.MASTER_FLAG, *be.FLAGS.values(), be.SNAPSHOT_ENV)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ALL:
        monkeypatch.delenv(k, raising=False)


def test_no_flag_is_set_in_any_committed_deploy_or_service_config():
    hits = []
    for pat in ("deploy", ".github", "systemd"):
        for p in (_REPO / pat).rglob("*") if (_REPO / pat).exists() else []:
            if p.is_file():
                try:
                    if "BRIEF_EVIDENCE" in p.read_text(errors="ignore"):
                        hits.append(str(p))
                except OSError:
                    pass
    assert hits == []


@pytest.mark.parametrize("val", ["", "0", "false", "no", "off"])
def test_falsey_values_do_not_enable(monkeypatch, val):
    for k in (be.MASTER_FLAG, *be.FLAGS.values()):
        monkeypatch.setenv(k, val)
    assert not any(be.enabled(b) for b in be.FLAGS)


def test_flags_off_means_no_database_read_and_no_snapshot_io(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise AssertionError("evidence layer touched while flags are off")
    monkeypatch.setattr(be, "load_events", boom)
    monkeypatch.setattr(be, "record_snapshot", boom)
    monkeypatch.setattr(be, "load_previous_snapshot", boom)
    monkeypatch.setenv(be.SNAPSHOT_ENV, str(tmp_path / "s.jsonl"))
    assert cb._evidence_lines("morning", 72) == [] and cb._evidence_lines("weekly", 168) == []
    from lib.comms import weekly
    assert weekly.evidence_lines_for([]) == []
    assert not (tmp_path / "s.jsonl").exists()


def test_flag_on_but_evidence_layer_fails_leaves_legacy_intact(monkeypatch):
    monkeypatch.setenv(be.MASTER_FLAG, "1")
    monkeypatch.setattr(be, "load_events", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    # Morning: a failing evidence query must not look like 'all quiet' - it yields the coverage-insufficient marker (the legacy brief
    # still renders, labelled). Weekly is unchanged: no evidence block.
    morning = cb._evidence_lines("morning", 72)
    assert morning and "EVIDENCE COVERAGE INSUFFICIENT" in morning[0]
    assert cb._evidence_lines("weekly", 168) == []
    from lib.comms import weekly
    monkeypatch.setattr(be, "build_evidence", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert weekly.evidence_lines_for([]) == []
    assert weekly.compose_weekly_brief([]) == weekly._compose_weekly_brief_core([])


def test_flag_on_without_snapshot_path_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("BRIEF_EVIDENCE_V1_WEEKLY", "1")
    monkeypatch.chdir(tmp_path)
    events = [{"id": "a", "title": "Power outage hits 20,000 customers in SA", "source": "ABC News", "geography": "AU",
               "collected_at": "2026-11-22T20:00:00Z", "url": "https://x/a"}]
    monkeypatch.setattr(be, "load_events", lambda *a, **k: events)
    out = cb._evidence_lines("weekly", 168)
    assert out and list(tmp_path.iterdir()) == []


# ── weekly capacity data-quality correction: independent flag, legacy output preserved when off ──
CAP = "BRIEF_CAPACITY_QUALITY_V1"
THIN = {"source": "pulse", "entries": [{"log_date": "2026-11-20", "energy": "low", "nervous_system": "tense", "body_signals": "ok"}]}


def test_capacity_flag_default_off_and_independent_of_evidence_flags(monkeypatch):
    monkeypatch.delenv(CAP, raising=False)
    monkeypatch.setenv(be.MASTER_FLAG, "1")
    for k in be.FLAGS.values():
        monkeypatch.setenv(k, "1")
    assert cb._capacity_quality_enabled() is False          # enabling every evidence flag does not enable the capacity correction
    monkeypatch.setenv(CAP, "1")
    assert cb._capacity_quality_enabled() is True


def test_capacity_flag_does_not_enable_evidence_foundation(monkeypatch):
    monkeypatch.setenv(CAP, "1")
    assert not any(be.enabled(b) for b in be.FLAGS)


def test_legacy_capacity_renderer_is_the_original_and_differs_from_corrected():
    legacy = "\n".join(cb._format_weekly_capacity_block(THIN))
    corrected = "\n".join(cb._format_weekly_capacity_block_v1(THIN))
    assert "Not enough observations" not in legacy and "Recovery confidence" in legacy
    assert "Not enough observations" in corrected and "Recovery confidence" not in corrected


def test_legacy_fetcher_does_not_filter_future_rows_corrected_does(monkeypatch):
    rows = [{"log_date": "2099-01-01"}, {"log_date": "2026-11-20"}]
    seen = []
    monkeypatch.setattr(cb, "_sb_get", lambda t, q="": seen.append(q) or (rows if t == "captains_log_entries" else []))
    assert cb._get_weekly_capacity(days=7)["entries"] == rows and not any("log_date=lte." in q for q in seen)
    seen.clear()
    out = cb._get_weekly_capacity_v1(days=7)
    assert all(r["log_date"] != "2099-01-01" for r in out["entries"]) and out.get("excluded_future") == 1
    assert any("log_date=lte." in q for q in seen)


def _stub_weekly(monkeypatch, calls):
    for name, value in {"_get_weekly_tech_signals": [], "_get_weekly_health_signals": [], "_generate_tech_osint_summary": None,
                        "_generate_health_osint_summary": None, "_get_weekly_content_activity": [], "_get_weekly_outage_alerts": [],
                        "_health_osint_collector_caveat": None}.items():
        monkeypatch.setattr(cb, name, lambda *a, _v=value, **k: _v)
    monkeypatch.setattr(cb, "_get_weekly_capacity", lambda days=7: calls.append("legacy_get") or {"source": "none", "entries": []})
    monkeypatch.setattr(cb, "_get_weekly_capacity_v1", lambda days=7: calls.append("v1_get") or {"source": "none", "entries": []})
    monkeypatch.setattr(cb, "_format_weekly_capacity_block", lambda c, days=7: calls.append("legacy_fmt") or ["LEGACY-CAPACITY"])
    monkeypatch.setattr(cb, "_format_weekly_capacity_block_v1", lambda c, days=7: calls.append("v1_fmt") or ["V1-CAPACITY"])
    from intelligence import db_size
    monkeypatch.setattr(db_size, "fetch_size_mb", lambda: None)


def test_weekly_report_uses_legacy_capacity_unless_capacity_flag_set(monkeypatch):
    calls: list[str] = []
    _stub_weekly(monkeypatch, calls)
    monkeypatch.setenv(be.MASTER_FLAG, "1")                  # every evidence flag on does not switch the capacity path
    for k in be.FLAGS.values():
        monkeypatch.setenv(k, "1")
    monkeypatch.setattr(be, "load_events", lambda *a, **k: [])
    text = cb.generate_weekly_report()
    assert "LEGACY-CAPACITY" in text and "V1-CAPACITY" not in text and calls == ["legacy_get", "legacy_fmt"]
    calls.clear()
    monkeypatch.setenv(CAP, "1")
    text = cb.generate_weekly_report()
    assert "V1-CAPACITY" in text and "LEGACY-CAPACITY" not in text and calls == ["v1_get", "v1_fmt"]
