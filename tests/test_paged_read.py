"""Complete retrieval through a data API that cuts every request at a row maximum. All data is synthetic."""
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

import pytest

from intelligence import brief_evidence as be
from intelligence import captains_brief as cb
from intelligence import paged_read as pr

NOW = datetime(2026, 11, 27, 7, 0, tzinfo=timezone.utc)


def stamp(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat()


def row(i: int, minutes_ago: float, **extra) -> dict:
    return {"event_id": f"e{i:05d}", "collected_at": stamp(minutes_ago), "raw_title": f"Synthetic report {i}", **extra}


class Api:
    """Enough of PostgREST: eligibility, collected_at filters, the compound cursor, two-column descending order, limit, and a server
    maximum below any limit."""

    def __init__(self, rows, cap=1000, fail_on=None, on_call=None):
        self.rows, self.cap, self.fail_on, self.on_call, self.queries = list(rows), cap, fail_on, on_call, []

    def __call__(self, table, query):
        self.queries.append(query)
        if self.on_call:
            self.on_call(self, len(self.queries))
        if self.fail_on == len(self.queries):
            raise RuntimeError("synthetic failure")
        out = [r for r in self.rows if not r.get("suppressed")]
        limit, id_col = None, "event_id"
        when = lambda text: datetime.fromisoformat(text.strip('"').replace("Z", "+00:00"))
        for key, value in parse_qsl(query):
            op, _, arg = value.partition(".")
            if key == "collected_at":
                keep = {"gte": lambda a, b: a >= b, "lte": lambda a, b: a <= b}[op]
                out = [r for r in out if keep(when(r["collected_at"]), when(arg))]
            elif key == "or":
                older, tied = value[1:-1].split(",")
                ts, (col, _, last) = when(older.partition(".lt.")[2]), tied.partition(".lt.")
                out = [r for r in out if when(r["collected_at"]) < ts or r[col] < last.strip('"')]
            elif key == "limit":
                limit = int(value)
            elif key == "order":
                id_col = value.split(",")[1].split(".")[0]
        out.sort(key=lambda r: (when(r["collected_at"]), r[id_col]), reverse=True)
        return [dict(r) for r in out[: min(self.cap, limit or self.cap)]]


def once(rows):
    """A stand-in that holds one page of rows and nothing beyond it."""
    return lambda table, query="": [] if "&or=" in query else rows


def read(api, **kw):
    return pr.read_all(api, "intelligence_events", "select=event_id,collected_at", id_col="event_id", **kw)


def ids(rows):
    return [r["event_id"] for r in rows]


@pytest.mark.parametrize("count,cap", [(0, 1000), (1, 1000), (999, 1000), (1000, 1000), (1001, 1000), (3500, 1000), (250, 100)])
def test_every_row_once_whatever_the_server_maximum(count, cap):
    api = Api([row(i, i) for i in range(count)], cap=cap)
    got = read(api)
    assert got.complete and ids(got) == [f"e{i:05d}" for i in range(count)]


def test_rows_sharing_a_timestamp_across_a_page_edge_are_all_read_and_ordered_deterministically():
    rows = [row(i, i // 7) for i in range(2300)]
    first, second = read(Api(rows)), read(Api(list(reversed(rows))))
    assert first.complete and len(first) == 2300 and ids(first) == ids(second)


@pytest.mark.parametrize("ties,older,cap", [(150, 0, 100), (150, 5, 100), (2500, 3, 1000), (150, 0, 1000)])
def test_more_rows_on_one_timestamp_than_a_request_returns_are_all_read(ties, older, cap):
    rows = [row(i, 1) for i in range(ties)] + [row(9000 + i, 2 + i) for i in range(older)]
    got = read(Api(rows, cap=cap))
    assert got.complete and len(set(ids(got))) == len(got) == ties + older


@pytest.mark.parametrize("gone", ["already returned", "not yet returned"])
@pytest.mark.parametrize("cap", [2, 3])
def test_eligibility_changing_during_a_tied_read_loses_no_eligible_record(gone, cap):
    rows = [row(i, 1) for i in (1, 2, 3, 4)]
    victim = 3 if gone == "already returned" else 1             # 4 and 3 are on the first page

    def suppress(api, call):
        if call == 2:
            api.rows[victim - 1]["suppressed"] = True

    got = read(Api(rows, cap=cap, on_call=suppress))
    expected = {f"e{i:05d}" for i in (1, 2, 3, 4)} - ({"e00001"} if victim == 1 and cap < 4 else set())
    assert got.complete and set(ids(got)) == expected and len(ids(got)) == len(expected)


def test_records_becoming_eligible_behind_the_cursor_are_read():
    rows = [row(i, 1) for i in range(10)]
    rows[2]["suppressed"] = True

    def restore(api, call):
        if call == 2:
            api.rows[2]["suppressed"] = False

    got = read(Api(rows, cap=4, on_call=restore))
    assert got.complete and len(set(ids(got))) == 10


def test_a_repeated_page_is_not_completion():
    got = read(lambda table, query: [row(1, 1), row(2, 2)])
    assert not got.complete and got.reason == pr.NOT_ADVANCING and len(got) == 2


@pytest.mark.parametrize("missing", ["collected_at", "event_id"])
@pytest.mark.parametrize("later", [False, True])
def test_a_row_without_its_cursor_field_is_not_completion_however_short_the_page(missing, later):
    bad = {k: v for k, v in row(9, 9).items() if k != missing}
    pages = [[row(1, 1)], [bad]] if later else [[bad]]
    got = read(lambda table, query: pages.pop(0) if pages else [])
    assert not got.complete and got.reason == pr.NO_KEY and len(got) == (2 if later else 1)


@pytest.mark.parametrize("response", [None, {"message": "synthetic error"}])
def test_a_response_that_is_not_a_list_is_not_an_empty_window(response):
    got = read(lambda table, query: response)
    assert not got.complete and got.reason == pr.BAD_RESPONSE and got == []


@pytest.mark.parametrize("failing_call", [1, 2, 3])
def test_a_failed_page_is_never_taken_for_the_end(failing_call):
    got = read(Api([row(i, i) for i in range(2500)], fail_on=failing_call))
    assert not got.complete and got.reason == pr.PAGE_FAILED and len(got) < 2500


def test_rows_arriving_during_the_read_do_not_shift_or_duplicate_pages():
    def insert(api, call):
        api.rows.append(row(9000 + call, -call))        # newer than everything already read
    got = read(Api([row(i, i) for i in range(2500)], on_call=insert))
    assert len(ids(got)) == len(set(ids(got))) and {f"e{i:05d}" for i in range(2500)} <= set(ids(got))


def test_the_safety_limit_is_reported():
    got = read(Api([row(i, i) for i in range(300)], cap=100), max_rows=200)
    assert not got.complete and got.reason == pr.ROW_LIMIT and len(got) == 200


def test_load_events_reads_past_one_request_and_keeps_the_oldest_report():
    rows = [row(i, i * 2, intelligence_source_registry={"source_name": "Synthetic Wire"}) for i in range(2100)]     # 70 h
    events = be.load_events(Api(rows), hours=72, now=NOW)
    assert events.complete and len(events) == 2100 and events[-1]["id"] == "e02099"
    assert be.retrieval_note(events, 72) is None


def test_an_incomplete_read_says_so_with_its_reach():
    rows = [row(i, i * 2) for i in range(2100)]
    events = be.load_events(Api(rows, fail_on=2), hours=72, now=NOW)
    note = be.retrieval_note(events, 72)
    assert len(events) == 1000 and "incomplete" in note and "1000 report(s) read" in note and "reaching back to 2026-11-25 21:42 UTC" in note


def test_a_read_that_fails_outright_is_empty_and_marked():
    events = be.load_events(Api([], fail_on=1), hours=72, now=NOW)
    assert events == [] and not events.complete


def test_plain_lists_are_not_reported_as_incomplete():
    assert be.retrieval_note([], 72) is None


def test_caveat_joining():
    assert cb._with_retrieval_note(None, None) is None
    assert cb._with_retrieval_note("Two sources failed.", None) == "Two sources failed."
    assert cb._with_retrieval_note("Two sources failed.", "Report retrieval was incomplete") == "Two sources failed; Report retrieval was incomplete"


@pytest.mark.parametrize("name,id_col", [("_get_weekly_tech_signals", "event_id"), ("_get_weekly_health_signals", "signal_id")])
def test_weekly_roll_up_counts_the_whole_week_and_keeps_rank_order(monkeypatch, name, id_col):
    now = datetime.now(timezone.utc)
    rows = [{id_col: f"s{i:05d}", "collected_at": (now - timedelta(minutes=3 * i)).isoformat(), "rank_score": None if i == 2400 else i % 90}
            for i in range(2500)]
    monkeypatch.setattr(cb, "_sb_request", Api(rows))
    got = getattr(cb, name)(days=7)
    assert got.complete and len(got) == 2500
    assert got[0]["rank_score"] is None and [r["rank_score"] for r in got[1:]] == sorted((r["rank_score"] for r in got[1:]), reverse=True)


def test_weekly_block_discloses_an_incomplete_read():
    rows = pr.PagedRead([{"confidence_level": "HIGH", "title": "Synthetic", "rank_score": 1}], complete=False, reason=pr.PAGE_FAILED)
    text = "\n".join(cb._format_weekly_osint_block("TECH OSINT", "x", rows, "confidence_level", "title"))
    assert "Retrieval was incomplete" in text
    empty = pr.PagedRead(complete=False, reason=pr.PAGE_FAILED)
    text = "\n".join(cb._format_weekly_osint_block("TECH OSINT", "x", empty, "confidence_level", "title"))
    assert "Retrieval failed" in text and "No signals collected" not in text


# ── a failed read stays distinguishable from an empty window, in every brief and fallback path ────────────────────────

def _failing(table, query=""):
    raise RuntimeError("synthetic outage")


def _empty(table, query=""):
    return []


@pytest.fixture
def quiet(monkeypatch):
    """Everything around the report read is stubbed, so only the read differs."""
    for name, value in {"_get_latest_ori_brief": None, "_get_capacity_today": None, "_get_infra_verification": None,
                        "_get_todays_morning_record": None, "_get_todays_morning_brief_text": None, "_get_previous_morning_record": None,
                        "_get_previous_evening_record": None, "_theme_lines": [], "_health_lines": [], "_coverage_lines": [],
                        "_format_capacity_block": [], "_format_infra_block": [], "_format_intelligence_posture_block": []}.items():
        monkeypatch.setattr(cb, name, lambda *a, _v=value, **k: _v)
    monkeypatch.setattr(cb, "build_daily_digest", None)
    monkeypatch.setattr(cb, "_sb_get", _empty)
    for flag in ("BRIEF_EVIDENCE_V1", "BRIEF_EVIDENCE_V1_MORNING", "BRIEF_EVIDENCE_V1_WEEKLY", "BRIEF_MORNING_PDB_V1",
                 "BRIEF_EOD_ASSESSMENT_V1"):
        monkeypatch.delenv(flag, raising=False)
    return monkeypatch


def _morning():
    gap = type("Gap", (), {"missed": False, "lookback_hours": 24})()
    return cb.generate_morning_brief(gap=gap)


@pytest.mark.parametrize("flags", [("BRIEF_MORNING_PDB_V1", "BRIEF_EVIDENCE_V1_MORNING"), ("BRIEF_MORNING_PDB_V1",),
                                   ("BRIEF_EVIDENCE_V1_MORNING",), ()])
def test_morning_paths_tell_a_failed_read_from_an_empty_window(quiet, flags):
    for flag in flags:
        quiet.setenv(flag, "1")
    quiet.setattr(cb, "_sb_request", _failing)
    failed = _morning()
    quiet.setattr(cb, "_sb_request", _empty)
    empty = _morning()
    assert "read failed" in failed.lower() or "retrieval failed" in failed.lower()
    assert "read failed" not in empty.lower() and "retrieval failed" not in empty.lower() and failed != empty


@pytest.mark.parametrize("flags", [("BRIEF_EOD_ASSESSMENT_V1",), ()])
def test_evening_paths_tell_a_failed_read_from_an_empty_window(quiet, flags):
    for flag in flags:
        quiet.setenv(flag, "1")
    quiet.setattr(cb, "_sb_request", _failing)
    failed = cb.generate_eod_summary()
    quiet.setattr(cb, "_sb_request", _empty)
    empty = cb.generate_eod_summary()
    assert "read failed" in failed.lower() or "retrieval failed" in failed.lower()
    assert "read failed" not in empty.lower() and "retrieval failed" not in empty.lower()


def test_weekly_evidence_and_roll_up_tell_a_failed_read_from_an_empty_week(quiet):
    quiet.setenv("BRIEF_EVIDENCE_V1_WEEKLY", "1")
    quiet.setattr(cb, "_sb_request", _failing)
    failed = "\n".join(cb._evidence_lines("weekly", 168) + cb._format_weekly_osint_block(
        "TECH OSINT", "x", cb._get_weekly_tech_signals(), "osint_confidence_level", "raw_title"))
    quiet.setattr(cb, "_sb_request", _empty)
    empty_evidence = cb._evidence_lines("weekly", 168)
    empty = "\n".join(cb._format_weekly_osint_block("TECH OSINT", "x", cb._get_weekly_tech_signals(), "osint_confidence_level", "raw_title"))
    assert "Report retrieval failed" in failed and "Retrieval failed" in failed and "No signals collected" not in failed
    assert empty_evidence == [] and "No signals collected" in empty and "failed" not in empty
