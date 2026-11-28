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
    """Enough of PostgREST: collected_at filters, two-column descending order, limit, and a server maximum below any limit."""

    def __init__(self, rows, cap=1000, fail_on=None, on_call=None):
        self.rows, self.cap, self.fail_on, self.on_call, self.queries = list(rows), cap, fail_on, on_call, []

    def __call__(self, table, query):
        self.queries.append(query)
        if self.on_call:
            self.on_call(self, len(self.queries))
        if self.fail_on == len(self.queries):
            raise RuntimeError("synthetic failure")
        out, limit, id_col, offset = list(self.rows), None, "event_id", 0
        for key, value in parse_qsl(query):
            op, _, arg = value.partition(".")
            if key == "collected_at":
                keep = {"gte": lambda a, b: a >= b, "lte": lambda a, b: a <= b, "lt": lambda a, b: a < b}[op]
                out = [r for r in out if keep(datetime.fromisoformat(r["collected_at"]), datetime.fromisoformat(arg.replace("Z", "+00:00")))]
            elif key == "limit":
                limit = int(value)
            elif key == "offset":
                offset = int(value)
            elif key == "order":
                id_col = value.split(",")[1].split(".")[0]
        out.sort(key=lambda r: (datetime.fromisoformat(r["collected_at"]), r[id_col]), reverse=True)
        return [dict(r) for r in out[offset : offset + min(self.cap, limit or self.cap)]]


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


def test_a_getter_that_ignores_the_cursor_ends():
    got = read(lambda table, query: [row(1, 1), row(2, 2)])
    assert got.complete and len(got) == 2


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
    assert "Retrieval was incomplete" in text and "No signals collected" not in text
