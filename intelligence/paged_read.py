"""Complete, deterministic reads through the data API, which returns a limited number of rows per request.

A single request with a large ``limit`` is silently cut to the server's maximum, so rows are read newest first in pages that resume at the
oldest timestamp already seen (the boundary rows come back again and are dropped by id). Where more rows share that timestamp than one
request returns, an offset walks through them. A short page is never taken to mean the end, because the server's maximum can be lower
than the page asked for: the read ends only on an empty page. The result says whether it is complete and, if not, why.

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


class PagedRead(list):
    """The rows, newest first, plus whether they are all of them. A plain list to every existing reader."""

    def __init__(self, rows=(), *, complete: bool = True, reason: str = ""):
        super().__init__(rows)
        self.complete = complete
        self.reason = reason


def read_all(get, table: str, query: str, *, id_col: str, time_col: str = "collected_at", page_size: int = PAGE_SIZE,
             max_rows: int = MAX_ROWS) -> PagedRead:
    """All rows matching ``query`` (filters and ``select`` only: no order, limit or offset), ordered by ``time_col`` then ``id_col``,
    both descending. ``select`` must include both columns. Never raises."""
    rows: list = []
    seen: set = set()
    cursor: str | None = None
    offset = 0                  # rows to skip from the cursor; non-zero only to pass rows already seen at one timestamp
    stale = 0                   # consecutive pages with nothing new
    reason = ""
    while True:
        page_query = f"{query}&order={time_col}.desc,{id_col}.desc&limit={page_size}"
        if cursor is not None:
            page_query += f"&{time_col}=lte.{quote(cursor, safe='')}"
        if offset:
            page_query += f"&offset={offset}"
        try:
            batch = get(table, page_query) or []
        except Exception as exc:  # noqa: BLE001 - reported through the result, not raised: a brief is never blocked by the read
            log.warning("paged read of %s failed after %d row(s): %s", table, len(rows), exc)
            reason = PAGE_FAILED
            break
        if not batch:
            break
        if any(r.get(id_col) is None or not r.get(time_col) for r in batch):
            if cursor is None:
                rows = list(batch)
                if len(batch) >= page_size:
                    reason = NO_KEY
            else:
                reason = NO_KEY
            break
        new = [r for r in batch if r[id_col] not in seen]
        if new:
            seen.update(r[id_col] for r in new)
            rows += new
            if len(rows) > max_rows:
                del rows[max_rows:]
                reason = ROW_LIMIT
                break
            stale = 0
        else:
            stale += 1
            if stale > 1:       # a getter that ignores the cursor and offset; nothing more can be learned from it
                break
        last = str(batch[-1][time_col])
        if new and last != cursor:
            cursor, offset = last, 0
        else:
            offset += len(batch)
    return PagedRead(rows, complete=not reason, reason=reason)
