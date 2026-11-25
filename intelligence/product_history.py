"""Append-only assessment history for the analytical products (pure logic; the database sits behind a small gateway).

Concepts kept separate on purpose:
  * generation  - a stored assessment whose CONTENT differs from the previous one (insert-only, never updated or deleted);
  * refresh     - a successful (or failed) reassessment run. Every run is recorded, including runs whose content is identical
                  to the current generation; those add a refresh record and no generation.
Freshness is computed from the latest successful refresh, so an identical-content refresh neither pretends the content changed
nor looks like a missed run, and the date the content last changed stays visible beside it.

Nothing here infers history that was not recorded: legacy rows carry explicit *_basis labels (see the 0263a draft migration).

Works on migration 0263a alone (old primary key kept: a same-day overwrite is archived by the database and the view still
exposes the latest assessment per cadence) and on 0263a+0263b (every generation is its own row).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from typing import Any, Protocol

from intelligence.reporting_time import (
    MELBOURNE,
    age_hours,
    reporting_date,
    to_melbourne,
)

log = logging.getLogger(__name__)

WRITER_VERSION = 2
CONTENT_FIELDS = ("title", "summary", "sections", "exceptions", "body_md")

# Schedule (Melbourne wall clock), mirrored from intel_products_job.register_jobs.
DAILY_SLOT = (6, 20)
WEEKLY_SLOT = (0, 7, 20)  # Monday=0, 07:20
# PROPOSAL (needs Captain confirmation): a refresh slot must have completed by slot start + 25 min (daily 06:45, weekly Mon 07:45).
# Observed run time is ~2 min after the 06:20 slot; the 07:00 morning brief is the consumption instant, so the deadline has to fall
# before it or "Refresh overdue" can never be shown there (the earlier 45 min grace put the deadline at 07:05, after the brief).
COMPLETION_GRACE = timedelta(minutes=25)
# A successful refresh up to this long BEFORE the slot start (a manual run at 06:10 while the slot at 06:20 was skipped) still
# satisfies the slot.
SLOT_EARLY_TOLERANCE = timedelta(minutes=30)
USABLE_MAX_HOURS = {"daily": 36.0, "weekly": 8 * 24.0}
UNKNOWN_CADENCE_MAX_HOURS = 36.0


class UniqueViolation(Exception):
    """Raised by a gateway when an insert collides with an existing key.

    legacy_key=True: the collision is on the ORIGINAL primary key (product_key, generated_for), i.e. migration 0263b has not been
    applied. The previous version is archived by the 0263a trigger when the gateway overwrites it (`overwrite_generation`).
    """

    def __init__(self, message: str = "", *, legacy_key: bool = False):
        super().__init__(message)
        self.legacy_key = legacy_key


class Gateway(Protocol):
    def latest_generation(self, product_key: str, cadence: str) -> dict | None:
        """Newest stored generation of (product, cadence) by GENERATION TIME (as_of, then id), never by reporting_date."""

    def max_generation_seq(self, product_key: str, cadence: str, reporting_date: str) -> int:
        """Highest generation_seq stored for exactly this (product, cadence, reporting_date); 0 when none."""

    def insert_generation(self, rec: dict) -> dict: ...
    def insert_refresh(self, rec: dict) -> None: ...
    # Optional (0263a-only databases): overwrite the row holding the original key; the database archives the old version.
    # def overwrite_generation(self, rec: dict) -> dict


# ---------------------------------------------------------------- hashing / lineage


def canonical_content(rec: dict) -> str:
    return json.dumps(
        {k: rec.get(k) for k in CONTENT_FIELDS}, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def content_hash(rec: dict) -> str:
    return hashlib.sha256(canonical_content(rec).encode("utf-8")).hexdigest()


def input_watermark(rows: list[dict], window_days: int) -> dict:
    """What evidence the assessment read: count, newest collection time, and a hash of the sorted event ids."""
    ids = sorted(str(r.get("event_id")) for r in rows)
    collected = [str(r["collected_at"]) for r in rows if r.get("collected_at")]
    return {
        "schema": 1,
        "event_count": len(rows),
        "max_collected_at": max(collected) if collected else None,
        "id_hash": hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest(),
        "window_days": window_days,
    }


def change_summary(prev: dict | None, new: dict) -> dict:
    """Facts only: which content fields differ and which exception dedupe_keys appeared or disappeared."""
    if prev is None:
        return {"first_generation": True}
    changed = [k for k in CONTENT_FIELDS if prev.get(k) != new.get(k)]

    def keys(r):
        return {str(e.get("dedupe_key")) for e in (r.get("exceptions") or []) if isinstance(e, dict) and e.get("dedupe_key")}

    pk, nk = keys(prev), keys(new)
    return {
        "first_generation": False,
        "changed_fields": changed,
        "body_md_chars_before": len(prev.get("body_md") or ""),
        "body_md_chars_after": len(new.get("body_md") or ""),
        "exception_keys_added": sorted(nk - pk),
        "exception_keys_removed": sorted(pk - nk),
    }


# ---------------------------------------------------------------- append protocol


@dataclass
class RunResult:
    outcome: str  # new_generation | unchanged
    generation_id: Any
    generation_seq: int
    content_hash: str
    attempts: int = 1


def build_generation(rec: dict, *, cadence: str, legacy_attribution: bool, watermark: dict | None) -> dict:
    """Extend a legacy-shaped record (`to_records`) with the history columns.

    legacy_attribution=True (flag OFF after the key swap): attribution stays exactly the legacy one (UTC date of as_of, cadence
    unknown) so only the storage is append-only; no new meaning is claimed.
    """
    as_of = datetime.fromisoformat(rec["as_of"])
    out = dict(rec)
    if legacy_attribution:
        out["reporting_date"] = as_of.astimezone(timezone.utc).date().isoformat()
        out["generated_for"] = out["reporting_date"]
        out["reporting_date_basis"] = "legacy_utc_key"
        out["cadence"] = "unknown"
        out["cadence_basis"] = "legacy_unknown"
    else:
        out["reporting_date"] = reporting_date(as_of).isoformat()
        out["generated_for"] = out["reporting_date"]
        out["reporting_date_basis"] = "writer_melbourne"
        out["cadence"] = cadence if cadence in ("daily", "weekly") else "unknown"
        out["cadence_basis"] = "job" if cadence in ("daily", "weekly") else "caller_unspecified"
    out["input_watermark"] = watermark
    out["content_hash"] = content_hash(rec)
    out["writer_version"] = WRITER_VERSION
    return out


def record_run(gw: Gateway, gen: dict, *, max_attempts: int = 6) -> RunResult:
    """Append a generation only when content differs from the latest one, and always record the refresh.

    "Latest" is the newest by generation time (as_of), so rows attributed by different date conventions (UTC legacy key vs
    Melbourne reporting date) cannot confuse the choice; the sequence number is max(seq)+1 for the exact
    (product, cadence, reporting_date) key. Safe for two concurrent writers on the same key: the unique key makes the loser
    retry, re-read, and (if the winner stored identical content) record an `unchanged` refresh.
    """
    pk, cadence = gen["product_key"], gen["cadence"]
    for attempt in range(1, max_attempts + 1):
        # Read the sequence BEFORE the latest row: a concurrent writer that commits in between is then seen as `latest` (identical
        # content -> unchanged) or collides on the sequence key (retry); reading in the other order could append a duplicate.
        top_seq = gw.max_generation_seq(pk, cadence, gen["reporting_date"])
        latest = gw.latest_generation(pk, cadence)
        if latest is not None and content_hash(latest) == gen["content_hash"]:
            outcome, gid, seq = "unchanged", latest["id"], latest["generation_seq"]
        else:
            seq = top_seq + 1
            rec = dict(gen)
            rec["generation_seq"] = seq
            rec["supersedes_id"] = latest["id"] if latest is not None else None
            summary = change_summary(latest, gen)
            summary["write_id"] = uuid.uuid4().hex   # per-write nonce: lets the database tell this writer from the original one
            rec["change_summary"] = summary
            try:
                stored = gw.insert_generation(rec)
            except UniqueViolation as uv:
                overwrite = getattr(gw, "overwrite_generation", None)
                if not (uv.legacy_key and overwrite):
                    continue
                # 0263a only: the original key still exists, so a second generation of the same key replaces the row and the
                # database archives the previous version (revisions table). Lineage then lives in that archive, not in supersedes_id.
                rec["supersedes_id"] = None
                rec["change_summary"] = {**summary, "previous_version_archived": True}
                stored = overwrite(rec)
            outcome, gid = "new_generation", stored["id"]
        gw.insert_refresh(
            {
                "product_key": pk,
                "cadence": cadence,
                "reporting_date": gen["reporting_date"],
                "as_of": gen["as_of"],
                "outcome": outcome,
                "generation_id": gid,
                "generation_seq": seq,
                "input_watermark": gen.get("input_watermark"),
                "content_hash": gen["content_hash"],
                "writer_version": WRITER_VERSION,
            }
        )
        return RunResult(outcome, gid, seq, gen["content_hash"], attempt)
    raise RuntimeError(f"could not append generation for {pk}/{cadence} after {max_attempts} attempts")


def record_failure(gw: Gateway, *, product_key: str, cadence: str, as_of: datetime, error: BaseException) -> None:
    """Failed attempt record (class name only, no message text). Never raises."""
    try:
        gw.insert_refresh(
            {
                "product_key": product_key,
                "cadence": cadence,
                "reporting_date": reporting_date(as_of).isoformat(),
                "as_of": as_of.isoformat(),
                "outcome": "failed",
                "error_class": type(error).__name__,
                "writer_version": WRITER_VERSION,
            }
        )
    except Exception as exc:  # noqa: BLE001 - failure bookkeeping must never mask the original error
        log.debug("could not record failed refresh (%s)", type(exc).__name__)


# ---------------------------------------------------------------- freshness


class Freshness(str, Enum):
    CURRENT = "Current"
    REFRESH_OVERDUE = "Refresh overdue"
    STALE = "Stale"
    UNAVAILABLE = "Unavailable"


@dataclass
class FreshnessResult:
    state: Freshness
    age_hours: float | None
    last_success: datetime | None
    expected_deadline: datetime | None
    reason: str = ""
    usable_max_hours: float = 0.0
    last_failed: datetime | None = None
    failed_since_success: bool = False


def latest_slot(now: datetime, cadence: str) -> tuple[datetime, datetime] | None:
    """(start, completion deadline) of the most recent scheduled slot that has started; None when cadence has no schedule."""
    m = to_melbourne(now)
    if cadence == "daily":
        hh, mm = DAILY_SLOT
        start = datetime.combine(m.date(), time(hh, mm), tzinfo=MELBOURNE)
        if start > m:
            start = datetime.combine(m.date() - timedelta(days=1), time(hh, mm), tzinfo=MELBOURNE)
    elif cadence == "weekly":
        dow, hh, mm = WEEKLY_SLOT
        d = m.date() - timedelta(days=(m.weekday() - dow) % 7)
        start = datetime.combine(d, time(hh, mm), tzinfo=MELBOURNE)
        if start > m:
            start = datetime.combine(d - timedelta(days=7), time(hh, mm), tzinfo=MELBOURNE)
    else:
        return None
    return start, start + COMPLETION_GRACE


def freshness(now: datetime, cadence: str | None, last_success: datetime | None,
              last_failed: datetime | None = None) -> FreshnessResult:
    """Schedule-aware state from the latest SUCCESSFUL refresh instant (and the latest FAILED attempt, when known).

    Refresh overdue: the slot that should have completed by now has no successful refresh, although the previous assessment is
    still inside its usable age; OR the latest attempt for the current slot FAILED after the last success (the older assessment is
    then not "Current" even before the deadline, because the system knows the refresh did not happen).
    Stale: older than the usable maximum (36 h daily, 8 d weekly; 36 h when cadence is unknown).
    An unknown cadence never yields Refresh overdue from the schedule: no schedule is asserted for it; a recorded failure still does.
    """
    cad = cadence if cadence in ("daily", "weekly") else "unknown"
    mx = USABLE_MAX_HOURS.get(cad, UNKNOWN_CADENCE_MAX_HOURS)
    if last_success is None:
        return FreshnessResult(Freshness.UNAVAILABLE, None, None, None, "no successful refresh recorded", mx, last_failed)
    age = age_hours(last_success, now)
    slot = latest_slot(now, cad)
    deadline = slot[1] if slot else None
    failed_since = last_failed is not None and last_failed > last_success
    if age > mx:
        return FreshnessResult(Freshness.STALE, age, last_success, deadline, f"older than usable maximum {mx:g} h", mx,
                               last_failed, failed_since)
    if failed_since and (slot is None or last_failed >= slot[0] - SLOT_EARLY_TOLERANCE):
        return FreshnessResult(Freshness.REFRESH_OVERDUE, age, last_success, deadline,
                               "latest refresh attempt failed after the last success", mx, last_failed, True)
    if slot and now >= slot[1] and last_success < slot[0] - SLOT_EARLY_TOLERANCE:
        return FreshnessResult(
            Freshness.REFRESH_OVERDUE, age, last_success, deadline, "scheduled refresh not completed by its deadline", mx,
            last_failed, failed_since
        )
    reason = "cadence unknown: no schedule asserted" if cad == "unknown" else ""
    return FreshnessResult(Freshness.CURRENT, age, last_success, deadline, reason, mx, last_failed, failed_since)


# ---------------------------------------------------------------- storage growth


@dataclass
class GrowthReport:
    generations: int = 0
    refreshes: int = 0
    content_bytes: int = 0
    by_product: dict = field(default_factory=dict)
    span_days: float = 0.0
    projected_bytes_per_year: int = 0


def storage_growth_report(generations: list[dict], refresh_count: int = 0) -> GrowthReport:
    """Content volume of stored generations and a linear 365-day projection. Pure; feed it a SELECT export.

    Counts the JSON text of the content columns only (not index or TOAST overhead); use GROWTH_SQL for on-disk size.
    """
    rep = GrowthReport(generations=len(generations), refreshes=refresh_count)
    stamps = []
    for g in generations:
        size = len(canonical_content(g).encode("utf-8"))
        rep.content_bytes += size
        p = rep.by_product.setdefault(g.get("product_key"), {"generations": 0, "content_bytes": 0})
        p["generations"] += 1
        p["content_bytes"] += size
        if g.get("as_of"):
            stamps.append(datetime.fromisoformat(str(g["as_of"])))
    if len(stamps) >= 2:
        rep.span_days = max((max(stamps) - min(stamps)).total_seconds() / 86400.0, 1.0)
        rep.projected_bytes_per_year = int(rep.content_bytes / rep.span_days * 365)
    return rep


GROWTH_SQL = (
    "select 'intelligence_products' t, count(*) n, pg_total_relation_size('public.intelligence_products') bytes from public.intelligence_products "
    "union all select 'intelligence_product_refreshes', count(*), pg_total_relation_size('public.intelligence_product_refreshes') "
    "from public.intelligence_product_refreshes"
)
