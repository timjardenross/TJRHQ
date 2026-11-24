"""Ingestion wiring for original-publisher / original-date verification of aggregator (Google News) items.

Called once per collection run, AFTER events are classified and ranked and BEFORE they are persisted
(intelligence/scheduler.py -> annotate_events(ranked)). It decorates the in-memory events; the existing persistence path
(intelligence_store.save_event) then writes the outcome into the provenance columns / score_provenance. Nothing here writes to the
database or touches the brief directly.

SAFE BY CONSTRUCTION (the flag INTEL_ORIGINAL_PUBLISHER_VERIFY is already on in production):
  * Verification NEVER blocks, delays beyond a fixed wall-clock bound, or drops ingestion. annotate_events() never raises; any
    exception, timeout, budget block, missing config or flag-off leaves every event exactly as it was.
  * Hard bounds, env-configurable but clamped to absolute maxima so a bad env value cannot open the tap:
        INTEL_PUBVERIFY_MAX_PER_RUN        rendered fetches per collection run      default 5   (max 10)
        INTEL_PUBVERIFY_MAX_PER_DAY        rendered fetches per UTC day              default 20  (max 50)
        INTEL_PUBVERIFY_FETCH_TIMEOUT_S    per-fetch deadline                        default 20  (max 60)
        INTEL_PUBVERIFY_RUN_DEADLINE_S     total wall-clock for the whole step       default 90  (max 300)
        INTEL_PUBVERIFY_MAX_BUDGET_PCT     skip when the primary Firecrawl account is above this % of its safe ceiling
                                                                                      default 70  (max 90)
    The day count is read from the database (events already carrying a verification record for today) and also tracked in process;
    the larger wins. If the day count cannot be read, nothing is fetched (fail closed).
  * Every fetch goes through firecrawl_client.scrape -> external_fetch_budget.check_and_increment, so the account ceilings
    (primary 1,700 of 2,000/month; failover account 850 of 1,000) are enforced atomically by the existing circuit breaker. A budget
    refusal stops the step for this run and leaves the event stored exactly as today.
  * Date semantics are unchanged by default. published_at, published_at_basis and published_at_confidence keep the aggregator's CLAIM.
    The page's own timestamp, the delta and the outcome are recorded in score_provenance.publisher_verification. Only when
    INTEL_PUBVERIFY_PROMOTE_DATE=1 (default OFF) AND the publisher page carries a timezone-aware published-time is published_at replaced
    with it and labelled basis=feed / confidence=verified / label=publication; the freshness code already treats exactly that as VERIFIED.
    A modified-time, a date-only value or a zone-less time is never promoted (original_publisher.classify_fetch enforces this).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from intelligence import original_publisher as op
from intelligence import provenance as prov_mod

log = logging.getLogger(__name__)

RECORD_KEY = prov_mod.VERIFICATION_KEY
RECORD_VERSION = 1

DEFAULT_MAX_PER_RUN, HARD_MAX_PER_RUN = 5, 10
DEFAULT_MAX_PER_DAY, HARD_MAX_PER_DAY = 20, 50
DEFAULT_FETCH_TIMEOUT_S, HARD_FETCH_TIMEOUT_S = 20, 60
DEFAULT_RUN_DEADLINE_S, HARD_RUN_DEADLINE_S = 90, 300
DEFAULT_MAX_BUDGET_PCT, HARD_MAX_BUDGET_PCT = 70, 90
PROMOTE_FLAG = "INTEL_PUBVERIFY_PROMOTE_DATE"
BUDGET_PROVIDER = "firecrawl"


class BudgetBlocked(Exception):
    """The Firecrawl account budget (or its configuration) refused the fetch. Stops the step; the event is left untouched."""


def _env_int(name: str, default: int, hard_max: int) -> int:
    try:
        v = int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
    return max(0, min(v, hard_max))


@dataclass(frozen=True)
class Limits:
    per_run: int
    per_day: int
    fetch_timeout_s: int
    run_deadline_s: int
    max_budget_pct: int
    promote_date: bool


def limits() -> Limits:
    return Limits(
        per_run=_env_int("INTEL_PUBVERIFY_MAX_PER_RUN", DEFAULT_MAX_PER_RUN, HARD_MAX_PER_RUN),
        per_day=_env_int("INTEL_PUBVERIFY_MAX_PER_DAY", DEFAULT_MAX_PER_DAY, HARD_MAX_PER_DAY),
        fetch_timeout_s=max(1, _env_int("INTEL_PUBVERIFY_FETCH_TIMEOUT_S", DEFAULT_FETCH_TIMEOUT_S, HARD_FETCH_TIMEOUT_S)),
        run_deadline_s=max(1, _env_int("INTEL_PUBVERIFY_RUN_DEADLINE_S", DEFAULT_RUN_DEADLINE_S, HARD_RUN_DEADLINE_S)),
        max_budget_pct=_env_int("INTEL_PUBVERIFY_MAX_BUDGET_PCT", DEFAULT_MAX_BUDGET_PCT, HARD_MAX_BUDGET_PCT),
        promote_date=os.getenv(PROMOTE_FLAG, "0") == "1",
    )


# ── process-local memory: attempts today and URLs already tried (guards a restart-free re-run; the DB count guards restarts) ──────
_state_lock = threading.Lock()
_state: dict = {"day": None, "attempts": 0, "urls": set()}
_MAX_REMEMBERED_URLS = 2000


def _state_snapshot(day: str) -> tuple[int, set]:
    with _state_lock:
        if _state["day"] != day:
            _state.update(day=day, attempts=0, urls=set())
        return _state["attempts"], set(_state["urls"])


def _state_record(day: str, url: str | None) -> None:
    with _state_lock:
        if _state["day"] != day:
            _state.update(day=day, attempts=0, urls=set())
        _state["attempts"] += 1
        if url and len(_state["urls"]) < _MAX_REMEMBERED_URLS:
            _state["urls"].add(url)


def reset_state() -> None:                        # tests only
    with _state_lock:
        _state.update(day=None, attempts=0, urls=set())


# ── default collaborators (all injectable; all lazily imported so importing this module never touches the network or the DB) ─────
def _firecrawl_fetcher(url: str, timeout_s: int) -> dict | None:
    """Rendered fetch through the shared, budget-gated Firecrawl client. Returns {"url": final URL, "metadata": {...}}."""
    from intelligence.ingestion import external_fetch_budget, firecrawl_client
    try:
        data = firecrawl_client.scrape(url, formats=["markdown"], timeout=timeout_s)
    except (external_fetch_budget.FetchBudgetExceeded, external_fetch_budget.FetchBudgetCheckFailed,
            firecrawl_client.FirecrawlNotConfigured) as exc:
        raise BudgetBlocked(str(exc)) from exc
    meta = data.get("metadata") or {}
    return {"url": meta.get("url") or meta.get("sourceURL"), "metadata": meta}


def _db_day_count(day: str) -> int:
    """Events already persisted today with a verification record (one per rendered fetch). Raises when it cannot be read."""
    from intelligence.persistence import intelligence_store as store
    flt = json.dumps({RECORD_KEY: {"attempt_day": day}}, separators=(",", ":"))
    path = f"intelligence_events?score_provenance=cs.{urllib.parse.quote(flt, safe='')}&select=event_id&limit={HARD_MAX_PER_DAY + 1}"
    return len(store._get_strict(path))


def _budget_pct_used() -> float:
    from intelligence.ingestion import external_fetch_budget
    usage = external_fetch_budget.current_usage(BUDGET_PROVIDER)
    return float(usage["pct_of_ceiling"] or 0.0)


def _call_with_deadline(fn: Callable[[], object], timeout_s: float):
    """Run fn in a daemon thread and give up after timeout_s (raises TimeoutError). The abandoned thread cannot hold up the caller or
    interpreter exit; its own HTTP timeout ends it."""
    box: dict = {}

    def runner() -> None:
        try:
            box["v"] = fn()
        except BaseException as exc:                      # noqa: BLE001 - re-raised in the caller's thread
            box["e"] = exc

    t = threading.Thread(target=runner, name="pubverify-fetch", daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise TimeoutError(f"fetch exceeded {timeout_s}s")
    if "e" in box:
        raise box["e"]
    return box.get("v")


# ── event <-> item mapping and the record ───────────────────────────────────────────────────────────────────────────────────────
def _iso(v) -> str | None:
    return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v else None)


def _item(ev) -> dict:
    return {"id": str(getattr(ev, "event_id", "") or id(ev)), "source": getattr(ev, "source_name", "") or "", "title": getattr(ev, "raw_title", "") or "",
            "summary": getattr(ev, "raw_summary", "") or "", "geography": getattr(ev, "geography", None),
            "collected_at": getattr(ev, "collected_at", None), "published_at": getattr(ev, "published_at", None),
            "url": getattr(ev, "canonical_url", None)}


def _already_verified(ev) -> bool:
    p = getattr(ev, "provenance", None) or {}
    rec = p.get(RECORD_KEY) or {}
    return bool(rec) or (p.get("published_at_confidence") == "verified" and p.get("published_at_label") == "publication")


def _candidates(events, now: datetime, seen_urls: set) -> list:
    """Eligible, not suppressed, not already verified, one per canonical_url, highest rank first."""
    out, urls = [], set(seen_urls)
    for ev in events:
        try:
            url = getattr(ev, "canonical_url", None)
            if not url or url in urls or getattr(ev, "suppressed", False) or _already_verified(ev):
                continue
            if not op.eligible(_item(ev), now=now):
                continue
            urls.add(url)
            out.append(ev)
        except Exception as exc:                        # noqa: BLE001 - a malformed event is simply not a candidate
            log.debug("publisher verification: skipping malformed event: %s", exc)
    out.sort(key=lambda e: float(getattr(e, "rank_score", 0.0) or 0.0), reverse=True)
    return out


def build_record(ev, ver: op.Verification, *, day: str, now: datetime, promoted: bool, prior_domain: str | None) -> dict:
    claim = getattr(ev, "published_at", None)
    verified = ver.outcome == op.VERIFIED_DATE
    return {
        "v": RECORD_VERSION, "outcome": ver.outcome, "attempt_day": day, "attempted_at": _iso(now),
        "publisher_url": ver.publisher_url, "publisher_host": ver.publisher_host,
        "page_published_at": _iso(ver.published_at), "claimed_published_at": _iso(claim), "delta_hours": ver.delta_hours,
        # What the stored published_at is AFTER this step. 'claimed' = still the aggregator's claim; 'verified' = the publisher's own
        # timezone-aware published-time (only ever true when promoted).
        "date_status": "verified" if (verified and promoted) else "claimed",
        "page_date_verified": bool(verified), "promoted": promoted, "independence": "unproven", "reason": ver.reason,
        **({"prior_publisher_domain": prior_domain} if prior_domain else {}),
    }


def _apply(ev, ver: op.Verification, *, day: str, now: datetime, promote: bool) -> None:
    p = dict(getattr(ev, "provenance", None) or {})
    prior = p.get("publisher_domain")
    host_ok = bool(ver.publisher_host) and ver.outcome in (op.VERIFIED_DATE, op.PUBLISHER_KNOWN_DATE_UNVERIFIED) and bool(ver.publisher_url)
    if host_ok:
        dom = prov_mod.domain_of(ver.publisher_url)
        if dom and prior != dom:
            p["publisher_domain"] = dom
        if not p.get("publisher_family"):
            res = op.resolve_publisher(getattr(ev, "source_name", ""), getattr(ev, "raw_title", ""))
            if res.suffix_text:
                p["publisher_family"] = res.suffix_text
    promoted = False
    if promote and ver.outcome == op.VERIFIED_DATE and ver.published_at is not None and ver.published_at.utcoffset() is not None:
        collected = op.we._parse_ts(getattr(ev, "collected_at", None))
        if collected is None or ver.published_at <= collected + timedelta(hours=1):
            ev.published_at = ver.published_at
            p.update(published_at_basis="feed", published_at_precision="second", published_at_confidence="verified", published_at_label="publication")
            promoted = True
    new_dom = p.get("publisher_domain")
    p[RECORD_KEY] = build_record(ev, ver, day=day, now=now, promoted=promoted, prior_domain=prior if (prior and prior != new_dom) else None)
    ev.provenance = p


def _mark_attempt_failed(ev, *, day: str, now: datetime, reason: str) -> None:
    """A fetch that was attempted (and so may have cost a credit) but gave no usable page: record it so it counts towards the day cap
    and is never retried. The date and publisher columns are left exactly as they were."""
    p = dict(getattr(ev, "provenance", None) or {})
    p[RECORD_KEY] = build_record(ev, op.Verification(op.UNRESOLVED, reason=reason), day=day, now=now, promoted=False, prior_domain=None)
    ev.provenance = p


# ── the step ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def annotate_events(events, *, fetcher: Callable[[str, int], dict | None] | None = None, day_count_fn: Callable[[str], int] | None = None,
                    budget_pct_fn: Callable[[], float] | None = None, now: datetime | None = None, cfg: Limits | None = None) -> dict:
    """Verify at most per-run/per-day ELIGIBLE aggregator events and decorate them in place. Never raises; returns a stats dict."""
    stats = {"skipped": None, "candidates": 0, "attempted": 0, "verified": 0, "unverified": 0, "unresolved": 0, "failed": 0, "promoted": 0}
    try:
        return _annotate(events, stats, fetcher, day_count_fn, budget_pct_fn, now, cfg)
    except Exception as exc:                            # noqa: BLE001 - verification must never affect ingestion
        log.warning("publisher verification step aborted, events left as collected: %s", exc)
        stats["skipped"] = stats["skipped"] or f"error: {type(exc).__name__}"
        return stats


def _annotate(events, stats, fetcher, day_count_fn, budget_pct_fn, now, cfg) -> dict:
    if not op.enabled():
        stats["skipped"] = "flag_off"
        return stats
    if not prov_mod.columns_exist():
        stats["skipped"] = "provenance_columns_off"          # nowhere to store the outcome, so do not spend credits
        return stats
    cfg = cfg or limits()
    if cfg.per_run <= 0 or cfg.per_day <= 0:
        stats["skipped"] = "caps_zero"
        return stats
    now = now or datetime.now(timezone.utc)
    day = now.astimezone(timezone.utc).date().isoformat()
    attempts_today, seen_urls = _state_snapshot(day)
    cands = _candidates(events, now, seen_urls)
    stats["candidates"] = len(cands)
    if not cands:
        stats["skipped"] = "no_candidates"
        return stats
    try:
        used = max(attempts_today, (day_count_fn or _db_day_count)(day))
    except Exception as exc:                            # noqa: BLE001 - cannot prove we are under the day cap: do not fetch
        log.warning("publisher verification: day count unavailable (%s) - not fetching", exc)
        stats["skipped"] = "day_count_unavailable"
        return stats
    allowance = min(cfg.per_run, cfg.per_day - used)
    if allowance <= 0:
        stats["skipped"] = "day_cap_reached"
        return stats
    try:
        pct = (budget_pct_fn or _budget_pct_used)()
    except Exception as exc:                            # noqa: BLE001 - unverifiable budget: do not spend
        log.warning("publisher verification: Firecrawl budget unreadable (%s) - not fetching", exc)
        stats["skipped"] = "budget_unreadable"
        return stats
    if pct > cfg.max_budget_pct:
        stats["skipped"] = "budget_headroom_reserved"
        return stats

    fetch = fetcher or _firecrawl_fetcher
    deadline = time.monotonic() + cfg.run_deadline_s
    for ev in cands[:allowance]:
        remaining = deadline - time.monotonic()
        if remaining <= 1:
            stats["skipped"] = "run_deadline"
            break
        timeout = min(cfg.fetch_timeout_s, remaining)
        url = ev.canonical_url
        try:
            fetched = _call_with_deadline(lambda u=url, t=timeout: fetch(u, max(1, int(t))), timeout)
        except BudgetBlocked as exc:                    # refused BEFORE any credit was spent: leave the event untouched, stop for this run
            log.warning("publisher verification stopped by budget: %s", exc)
            stats["skipped"] = "budget_blocked"
            break
        except TimeoutError:
            _state_record(day, url)
            stats["attempted"] += 1
            stats["failed"] += 1
            _mark_attempt_failed(ev, day=day, now=now, reason="fetch timed out")
            stats["skipped"] = "timeout"
            break                                       # Firecrawl is slow: stop rather than stack more waits onto ingestion
        except Exception as exc:                        # noqa: BLE001 - a failed fetch is an outcome, never an error
            log.info("publisher verification fetch failed for %s: %s", url[:80], exc)
            _state_record(day, url)
            stats["attempted"] += 1
            stats["failed"] += 1
            _mark_attempt_failed(ev, day=day, now=now, reason=f"fetch failed: {type(exc).__name__}")
            continue
        _state_record(day, url)
        stats["attempted"] += 1
        try:
            ver = op.classify_fetch(_item(ev), fetched, now=now)
            _apply(ev, ver, day=day, now=now, promote=cfg.promote_date)
        except Exception as exc:                        # noqa: BLE001 - classification problem: event stays as collected
            log.warning("publisher verification classify failed: %s", exc)
            stats["failed"] += 1
            continue
        stats[{op.VERIFIED_DATE: "verified", op.PUBLISHER_KNOWN_DATE_UNVERIFIED: "unverified"}.get(ver.outcome, "unresolved")] += 1
        if ev.provenance.get(RECORD_KEY, {}).get("promoted"):
            stats["promoted"] += 1
    log.info("publisher verification: %s", stats)
    return stats
