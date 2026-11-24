"""Scheduled generation + persistence + weekly delivery of the intelligence products (default OFF).

Flags (all default OFF):
  INTEL_PRODUCTS_ENABLED=1            register and run the generation job (read-only SELECTs, one upsert per product)
  INTEL_PRODUCTS_WEEKLY_TELEGRAM=1    also send the weekly summary over the existing Telegram notification path

Persistence: table `intelligence_products` (DRAFT migration docs/migration-drafts/0261_intelligence_products.DRAFT.sql,
NOT applied). Until it is applied the upsert fails and the job logs the error; nothing else is affected.
Reads use GET only; the single write is an upsert into intelligence_products.
"""

from __future__ import annotations

import json
import logging
import os
import sys
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


def enabled(var="INTEL_PRODUCTS_ENABLED"):
    return os.environ.get(var, "0").strip().lower() in ("1", "true", "yes", "on")


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


def _get(table, query):
    url, headers = _cfg()
    req = urllib.request.Request(f"{url}/rest/v1/{table}?{query}", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310 - SUPABASE_URL env, https
        return json.loads(resp.read())


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
    rows, offset = [], 0
    while True:
        q = f"select={cols}&published_at=gte.{since_q}&order=published_at.asc&limit={PAGE}&offset={offset}"
        page = getter("intelligence_events", q)
        for r in page:
            r["source_name"] = names.get(r.pop("source_id", None), "")
        rows += page
        if len(page) < PAGE:
            return rows
        offset += PAGE


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
