"""Scheduled generation + persistence + weekly delivery of the intelligence products (default OFF).

Flags (all default OFF):
  INTEL_PRODUCTS_ENABLED=1            register and run the generation job (read-only SELECTs, one upsert per product)
  INTEL_PRODUCTS_WEEKLY_TELEGRAM=1    also send the weekly summary over the existing Telegram notification path
  INTEL_PRODUCTS_DAILY=0              (default ON once the job is enabled) switch off the daily refresh; the refresh only
                                      regenerates and upserts the stored products so the portal/workbench is never a week
                                      stale. It sends nothing.

Persistence: table `intelligence_products` (DRAFT migration docs/migration-drafts/0261_intelligence_products.DRAFT.sql,
NOT applied). Until it is applied the upsert fails and the job logs the error; nothing else is affected.
Reads use GET only; the single write is an upsert into intelligence_products.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "tools" / "intelligence" / "analytics"))

import intel_products as ip

TABLE = "intelligence_products"
LOOKBACK_DAYS = 90
PAGE = 1000


def enabled(var="INTEL_PRODUCTS_ENABLED", default="0"):
    return os.environ.get(var, default).strip().lower() in ("1", "true", "yes", "on")


def _cfg():
    url, key = (
        os.environ.get("SUPABASE_URL", ""),
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
    )
    if not url or not key:
        raise RuntimeError("Supabase not configured")
    return url, {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }


_RETRY_STATUSES = frozenset({500, 502, 503, 504})


def _get(table, query, *, attempts=3, sleep=time.sleep):
    url, headers = _cfg()
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(f"{url}/rest/v1/{table}?{query}", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310 - SUPABASE_URL env, https
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            # A transient gateway/statement-timeout error is retried with backoff; anything else fails at once.
            if exc.code not in _RETRY_STATUSES or attempt == attempts:
                raise
        except (TimeoutError, urllib.error.URLError):
            if attempt == attempts:
                raise
        sleep(2 * attempt)
    return []


def _keyset_pages(getter, cols, filter_q):
    """All rows matching `filter_q`, read in primary-key order with keyset paging.

    2026-11-24 live run: the first version read the whole window in one combined OR filter ordered by published_at with offset paging.
    intelligence_events has no index on published_at, so every page re-sorted ~35,000 rows (8 s, then a 500). Keyset paging on the
    primary key plus one simple filter per query keeps each page cheap and the read stable under concurrent inserts.
    """
    rows, last = [], None
    while True:
        after = f"&event_id=gt.{last}" if last else ""
        page = getter("intelligence_events", f"select={cols}&{filter_q}{after}&order=event_id.asc&limit={PAGE}")
        rows += page
        if len(page) < PAGE:
            return rows
        last = page[-1]["event_id"]


def fetch_rows(since, getter=_get):
    """SELECT-only export in the P1-P3 shape (source_name joined from the registry by id)."""
    names = {
        r["source_id"]: r["source_name"]
        for r in getter("intelligence_source_registry", "select=source_id,source_name")
    }
    cols = (
        "event_id,source_id,published_at,collected_at,canonical_url,raw_title,raw_summary,"
        "sector,geography,event_type,organisation"
    )
    since_q = urllib.parse.quote(since.isoformat())
    # Several feeds (AEMO notices, Fastly status, APRA/AusPayNet scrapes) carry no published_at. They are fetched by collected_at so a
    # completion notice or a whole feed is not silently invisible; the analytics treat an undated row explicitly, never as dated.
    dated = _keyset_pages(getter, cols, f"published_at=gte.{since_q}")
    undated = _keyset_pages(getter, cols, f"published_at=is.null&collected_at=gte.{since_q}")
    rows = dated + undated
    for r in rows:
        r["source_name"] = names.get(r.pop("source_id", None), "")
    # Same order the single query produced: undated first, then by publication time, event id as the tie-break.
    rows.sort(key=lambda r: (r.get("published_at") is not None, r.get("published_at") or "", r["event_id"]))
    return rows


def _upsert(record):
    url, headers = _cfg()
    headers = {
        **headers,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    q = urllib.parse.urlencode({"on_conflict": "product_key,generated_for"})
    req = urllib.request.Request(
        f"{url}/rest/v1/{TABLE}?{q}",
        data=json.dumps(record).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30):  # nosec B310 - SUPABASE_URL env, https
        return True


def to_records(products, as_of):
    return [
        {
            "product_key": p["product_key"],
            "generated_for": as_of.date().isoformat(),
            "as_of": as_of.isoformat(),
            "title": p["title"],
            "summary": p["summary"],
            "sections": p["sections"],
            "exceptions": p["exceptions"],
            "body_md": p["body_md"],
        }
        for p in products
    ]


def run(as_of=None, getter=_get, writer=_upsert, force=False):
    """Generate and persist. Returns the product list; [] when disabled."""
    if not (force or enabled()):
        log.info("[intel_products] disabled (set INTEL_PRODUCTS_ENABLED=1)")
        return []
    as_of = as_of or datetime.now(timezone.utc)
    rows = fetch_rows(as_of - timedelta(days=LOOKBACK_DAYS), getter)
    status = [r for r in rows if ip.pdr.is_status_source(r.get("source_name"))]
    context = [r for r in rows if not ip.pdr.is_status_source(r.get("source_name"))]
    products = ip.build_products(
        status, context, as_of, "scheduled read-only SELECT of intelligence_events"
    )
    for rec in to_records(products, as_of):
        writer(rec)
    return products


def send_weekly(products, as_of, notifier=None):
    if not enabled("INTEL_PRODUCTS_WEEKLY_TELEGRAM"):
        return False
    text = ip.weekly_message(
        products, os.environ.get("PORTAL_BASE_URL", "https://portal.invalid"), as_of
    )
    if notifier is None:
        sys.path.insert(0, str(_REPO))
        from core.platform.notification_service import Severity, Transport, notify

        def notifier(t):
            return notify(t, severity=Severity.INFO, transport=Transport.TELEGRAM).ok

    return bool(notifier(text))


def job_weekly():
    try:
        as_of = datetime.now(timezone.utc)
        products = run(as_of)
        if products:
            send_weekly(products, as_of)
    except Exception as exc:  # noqa: BLE001 - scheduled job must never take the scheduler down; logged
        log.error("[intel_products] job failed: %s", exc)


def job_daily():
    """Daily refresh of the stored products (no delivery): regenerate and upsert only."""
    try:
        run(datetime.now(timezone.utc))
    except Exception as exc:  # noqa: BLE001 - scheduled job must never take the scheduler down; logged
        log.error("[intel_products] daily refresh failed: %s", exc)


def register_jobs(scheduler, tz):
    """Registers the weekly job only when INTEL_PRODUCTS_ENABLED is on (default OFF)."""
    if not enabled():
        log.info("Intel products job disabled (set INTEL_PRODUCTS_ENABLED=1 to enable)")
        return
    from apscheduler.triggers.cron import CronTrigger

    scheduler.add_job(
        job_weekly,
        CronTrigger(day_of_week="mon", hour=7, minute=20, timezone=tz),
        id="intel_products_weekly",
        name="Intelligence products (weekly)",
        replace_existing=True,
    )
    log.info("Intel products weekly job registered (Mon 07:20)")
    if enabled("INTEL_PRODUCTS_DAILY", default="1"):
        # 06:20: the 06:00 collection heartbeat lands about 06:02 and generation takes about 2 minutes (57 s event read, rest
        # compute), so the products the 07:00 brief reads are from this morning and finish before the 06:55 brief window.
        # Same table, same upsert key (product_key, generated_for): a re-run on the same day replaces, never duplicates.
        scheduler.add_job(
            job_daily,
            CronTrigger(hour=6, minute=20, timezone=tz),
            id="intel_products_daily",
            name="Intelligence products (daily refresh)",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )
        log.info("Intel products daily refresh registered (06:20)")
