"""Scheduled generation + persistence + weekly delivery of the intelligence products (default OFF).

Flags (all default OFF):
  INTEL_PRODUCTS_ENABLED=1            register and run the generation job (read-only SELECTs, one upsert per product)
  INTEL_PRODUCTS_WEEKLY_TELEGRAM=1    also send the weekly summary over the existing Telegram notification path
  INTEL_PRODUCTS_DAILY=0              (default ON once the job is enabled) switch off the daily refresh; the refresh only
                                      regenerates and upserts the stored products so the portal/workbench is never a week
                                      stale. It sends nothing.

  INTEL_PRODUCTS_APPEND_V1=1          (default OFF) append-only assessment history: Melbourne reporting date, cadence, content-hash-gated
                                      generations, one refresh record per run (migration drafts 0263a/0263b, NOT applied). Works on 0263a alone.
                                      OFF = the original upsert, byte-for-byte; if the key swap (0263b) has been applied the OFF path falls back to
                                      append-only storage with the ORIGINAL attribution, so turning the flag off never overwrites history.

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

from intelligence import product_history as ph
from intelligence.reporting_time import iso_week_key, reporting_date

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "tools" / "intelligence" / "analytics"))

import intel_products as ip

TABLE = "intelligence_products"
REFRESH_TABLE = "intelligence_product_refreshes"
APPEND_FLAG = "INTEL_PRODUCTS_APPEND_V1"
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


def _post(table, record, *, returning=False, query="", merge=False):
    url, headers = _cfg()
    prefer = "return=representation" if returning else "return=minimal"
    if merge:
        prefer += ",resolution=merge-duplicates"
    headers = {**headers, "Content-Type": "application/json", "Prefer": prefer}
    req = urllib.request.Request(f"{url}/rest/v1/{table}{query}", data=json.dumps(record).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310 - SUPABASE_URL env, https
        body = resp.read()
    return json.loads(body)[0] if returning and body else None


def _conflict_is_legacy_key(exc):
    """True when a 409 is the ORIGINAL primary key (product_key, generated_for), i.e. 0263b has not been applied.

    PostgREST puts the Postgres constraint detail in the body, e.g. 'Key (product_key, generated_for)=(...) already exists.' The
    generation key reads 'Key (product_key, cadence, reporting_date, generation_seq)=...'. Unreadable body: not the legacy key
    (fail closed: the caller retries and finally raises, nothing is overwritten).
    """
    try:
        text = exc.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - body already consumed or unreadable
        return False
    return "(product_key, generated_for)" in text


class RestGateway:
    """History gateway over PostgREST: plain INSERTs (no on_conflict, no UPDATE, no DELETE) except `overwrite_generation`,
    used only on a 0263a-only database where the database trigger archives the replaced version."""

    def __init__(self, getter=_get, poster=_post):
        self._get, self._post = getter, poster

    def latest_generation(self, product_key, cadence):
        q = urllib.parse.urlencode(
            {"product_key": f"eq.{product_key}", "cadence": f"eq.{cadence}", "select": "*",
             "order": "as_of.desc,id.desc", "limit": "1"}
        )
        rows = self._get(TABLE, q)
        return rows[0] if rows else None

    def max_generation_seq(self, product_key, cadence, reporting_date):
        q = urllib.parse.urlencode(
            {"product_key": f"eq.{product_key}", "cadence": f"eq.{cadence}", "reporting_date": f"eq.{reporting_date}",
             "select": "generation_seq", "order": "generation_seq.desc", "limit": "1"}
        )
        rows = self._get(TABLE, q)
        return int(rows[0]["generation_seq"]) if rows else 0

    def insert_generation(self, rec):
        try:
            return self._post(TABLE, rec, returning=True)
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                raise ph.UniqueViolation(str(rec.get("generation_seq")), legacy_key=_conflict_is_legacy_key(exc)) from exc
            raise

    def overwrite_generation(self, rec):
        q = "?" + urllib.parse.urlencode({"on_conflict": "product_key,generated_for"})
        return self._post(TABLE, rec, returning=True, query=q, merge=True)

    def insert_refresh(self, rec):
        self._post(REFRESH_TABLE, rec)


def _key_mismatch(exc):
    """True when PostgREST rejected the legacy on_conflict target (42P10): the 0263 key swap has been applied."""
    if not isinstance(exc, urllib.error.HTTPError) or exc.code != 400:
        return False
    try:
        return "42P10" in exc.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - unreadable body: treat as some other 400
        return False


def _rekey_iso_week(products, as_of):
    """dedupe_key week suffix from the Melbourne reporting date (the analytics module derives it from the UTC instant)."""
    utc_wk = iso_week_key(as_of.astimezone(timezone.utc).date())
    mel_wk = iso_week_key(reporting_date(as_of))
    if utc_wk == mel_wk:
        return products
    for p in products:
        for e in p.get("exceptions") or []:
            k = e.get("dedupe_key")
            if isinstance(k, str) and k.endswith(":" + utc_wk):
                e["dedupe_key"] = k[: -len(utc_wk)] + mel_wk
    return products


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


def append_enabled():
    return enabled(APPEND_FLAG)


def run(as_of=None, getter=_get, writer=_upsert, force=False, cadence=None, gateway=None):
    """Generate and persist. Returns the product list; [] when disabled."""
    if not (force or enabled()):
        log.info("[intel_products] disabled (set INTEL_PRODUCTS_ENABLED=1)")
        return []
    as_of = as_of or datetime.now(timezone.utc)
    try:
        rows = fetch_rows(as_of - timedelta(days=LOOKBACK_DAYS), getter)
        status = [r for r in rows if ip.pdr.is_status_source(r.get("source_name"))]
        context = [r for r in rows if not ip.pdr.is_status_source(r.get("source_name"))]
        products = ip.build_products(
            status, context, as_of, "scheduled read-only SELECT of intelligence_events"
        )
    except Exception as exc:
        if append_enabled():
            # A failed reassessment must be on record, otherwise the previous assessment keeps looking current. Never raises.
            _record_generation_failure(cadence, as_of, exc, gateway)
        raise
    if not append_enabled():
        compat = None
        for rec in to_records(products, as_of):
            if compat is None:
                try:
                    writer(rec)
                    continue
                except Exception as exc:
                    if not _key_mismatch(exc):
                        raise
                    log.warning("[intel_products] legacy upsert key no longer exists; appending with legacy attribution")
                    compat = True
            _append(rec, cadence, rows, gateway, legacy_attribution=True)
        return products
    _rekey_iso_week(products, as_of)
    for rec in to_records(products, as_of):
        _append(rec, cadence, rows, gateway, legacy_attribution=False)
    return products


def _record_generation_failure(cadence, as_of, exc, gateway):
    try:
        gw = gateway or RestGateway()
    except Exception:  # noqa: BLE001 - bookkeeping only
        return
    cad = cadence if cadence in ("daily", "weekly") else "unknown"
    for key in ("recurring_provider", "systemic_risk", "forward_watch"):
        ph.record_failure(gw, product_key=key, cadence=cad, as_of=as_of, error=exc)


def _append(rec, cadence, rows, gateway, *, legacy_attribution):
    gw = gateway or RestGateway()
    gen = ph.build_generation(
        rec, cadence=cadence, legacy_attribution=legacy_attribution, watermark=ph.input_watermark(rows, LOOKBACK_DAYS)
    )
    try:
        res = ph.record_run(gw, gen)
    except Exception as exc:
        ph.record_failure(gw, product_key=rec["product_key"], cadence=gen["cadence"],
                          as_of=datetime.fromisoformat(rec["as_of"]), error=exc)
        raise
    log.info("[intel_products] %s %s generation %s (%s)", rec["product_key"], res.outcome, res.generation_seq, cadence)


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
        products = run(as_of, cadence="weekly")
        if products:
            send_weekly(products, as_of)
    except Exception as exc:  # noqa: BLE001 - scheduled job must never take the scheduler down; logged
        log.error("[intel_products] job failed: %s", exc)


def job_daily():
    """Daily refresh of the stored products (no delivery): regenerate and upsert only."""
    try:
        run(datetime.now(timezone.utc), cadence="daily")
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
