"""Complete, deterministic reads through the data API, which returns a limited number of rows per request.

A single request with a large ``limit`` is silently cut to the server's maximum, so rows are read newest first in pages. Each page starts
strictly after the last row of the one before, using the compound cursor (timestamp, id): rows ahead of the cursor can stop being
eligible, or new ones appear, without any row behind it moving, so nothing still eligible is skipped. No offsets are used. A short page is
never taken to mean the end, because the server's maximum can be lower than the page asked for.

The read is complete only when the server returns an empty page. Anything else that stops it (a failed request, a response that is not a
list, a row without its cursor fields, a page that repeats rows already read, the safety limit) is reported as incomplete.

``get(table, query)`` must RAISE on a failed request. A getter that returns [] on failure makes a failed page look like the end.
"""
from __future__ import annotations

import logging
from urllib.parse import quote

log = logging.getLogger(__name__)

PAGE_SIZE = 1000
MAX_ROWS = 20000      # safety stop, far above a week of reports; reaching it is reported, never silent

PAGE_FAILED = "a page of the read failed"
ROW_LIMIT = "the read stopped at its safety limit"
NO_KEY = "rows did not carry the fields needed to page"
NOT_ADVANCING = "the read returned rows it had already returned"
BAD_RESPONSE = "the read returned something other than a list of rows"


class PagedRead(list):
    """The rows, newest first, plus whether they are all of them. A plain list to every existing reader."""

    def __init__(self, rows=(), *, complete: bool = True, reason: str = ""):
        super().__init__(rows)
        self.complete = complete
        self.reason = reason


def read_all(get, table: str, query: str, *, id_col: str, time_col: str = "collected_at", page_size: int = PAGE_SIZE,
             max_rows: int = MAX_ROWS) -> PagedRead:
    """All rows matching ``query`` (filters and ``select`` only: no order, limit or offset), ordered by ``time_col`` then ``id_col``,
    both descending. ``select`` must include both columns, and ``id_col`` must be unique. Never raises."""
    rows: list = []
    seen: set = set()
    cursor: tuple[str, str] | None = None
    reason = ""
    while True:
        page_query = f"{query}&order={time_col}.desc,{id_col}.desc&limit={page_size}"
        if cursor is not None:
            at = quote(cursor[0], safe="")
            quoted_at, quoted_id = (quote(f'"{v}"', safe="") for v in cursor)
            # at or before the cursor time (index friendly), and either strictly before it or a lower id at that time
            page_query += f"&{time_col}=lte.{at}&or=({time_col}.lt.{quoted_at},{id_col}.lt.{quoted_id})"
        try:
            batch = get(table, page_query)
        except Exception as exc:  # noqa: BLE001 - reported through the result, not raised: a brief is never blocked by the read
            log.warning("paged read of %s failed after %d row(s): %s", table, len(rows), exc)
            reason = PAGE_FAILED
            break
        if not isinstance(batch, list):
            reason = BAD_RESPONSE
            break
        if not batch:
            break                                       # the only way a read is complete
        if any(not isinstance(r, dict) or r.get(id_col) is None or not r.get(time_col) for r in batch):
            rows += [r for r in batch if isinstance(r, dict)]
            reason = NO_KEY
            break
        new = []
        for r in batch:
            if r[id_col] not in seen:
                seen.add(r[id_col])
                new.append(r)
        rows += new
        if len(new) < len(batch):
            reason = NOT_ADVANCING
            break
        if len(rows) > max_rows:
            reason = ROW_LIMIT
            break
        cursor = (str(batch[-1][time_col]), str(batch[-1][id_col]))
    del rows[max_rows:]
    return PagedRead(rows, complete=not reason, reason=reason)
