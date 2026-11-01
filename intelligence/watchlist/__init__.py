"""Phase A watchlist tracking (post-brief materialisation detection)."""

from intelligence.watchlist.tracker import (
    WatchlistTracker,
    query_matches_event,
)

__all__ = ["WatchlistTracker", "query_matches_event"]
