"""Durable delivery recovery job (REPORT-ONLY by default).

Finds brief deliveries whose durable attempt records (``intelligence_delivery_attempts``, see delivery_record.py)
are not CONFIRMED, says what the delivery state machine would do about each, and emits one structured report
record that a deadman can consume. It is NOT registered anywhere: scheduler placement, privilege reduction and
activation belong to Production Operations (docs/intelligence/RECOVERY-JOB-REGISTRATION-SPEC.md).

Guarantees
* Report-only unless BOTH ``BRIEF_DELIVERY_RECOVERY_APPLY_V1`` and the delivery-record auto-resend flags are on
  (``delivery_record.auto_resend_enabled()``). Report-only performs no store write and no send: the "after
  recovery" view is computed on a throwaway in-memory copy.
* Idempotent and restart-safe: every decision is derived from the durable records; nothing is kept in process.
  Running it twice, or after a restart, cannot send twice (the state machine and the store's uniqueness guard
  refuse a second marked resend and a second primary).
* Never sends during a HOLD window (06:55-07:10, 12:25-12:40, 17:55-18:10 Australia/Melbourne), re-checked before
  every send; kill switch ``BRIEF_DELIVERY_RECOVERY_DISABLE`` is also re-checked before every send.
* Never resends on an ambiguous outcome except through ``delivery_record.deliver`` with
  ``AttemptKind.AUTHORISED_RECOVERY_RESEND``: at most ONE marked resend per brief version, only chunks not known
  to be confirmed, only when the stored text still hashes to the attempted content. Exactly-once is not claimed.
* A still-"sending" attempt is only treated as interrupted after a grace period, so a live send in another
  process is never marked ambiguous.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

from intelligence import delivery_record as dr

log = logging.getLogger(__name__)

SCHEMA = 1
KIND = "brief_delivery_recovery_report"
APPLY_FLAG = "BRIEF_DELIVERY_RECOVERY_APPLY_V1"
KILL_SWITCH = "BRIEF_DELIVERY_RECOVERY_DISABLE"
REPORT_PATH_ENV = "BRIEF_DELIVERY_RECOVERY_REPORT_PATH"
MELBOURNE = ZoneInfo("Australia/Melbourne")
HOLD_WINDOWS = ((6, 55, 7, 10), (12, 25, 12, 40), (17, 55, 18, 10))   # (start h, start m, end h, end m), inclusive
LOOKBACK_HOURS = 48
STALE_INTERRUPTED_MINUTES = 15       # a "sending" attempt younger than this may be a live send elsewhere
MIN_AMBIGUITY_AGE_MINUTES = 10       # apply only: do not resend within this long of the last ambiguous attempt
MAX_RECOVERY_AGE_HOURS = 12          # apply only: older briefs are reported, never resent
MAX_SENDS_PER_RUN = 3
_TRUE = ("1", "true", "yes", "on")

TextLoader = Callable[[str, str], str | None]   # (brief_table, brief_id) -> stored text, or None


def _truthy(name: str, env=None) -> bool:
    return (env if env is not None else os.environ).get(name, "").strip().lower() in _TRUE


def kill_switch_on(env=None) -> bool:
    return _truthy(KILL_SWITCH, env)


def apply_enabled(env=None) -> bool:
    """Apply needs this flag AND the delivery-record auto-resend flags (two independent default-OFF gates)."""
    e = env if env is not None else os.environ
    return _truthy(APPLY_FLAG, e) and _truthy(dr.FLAG, e) and _truthy(dr.AUTO_RESEND_FLAG, e)


def hold_window(now: datetime) -> str | None:
    """The HOLD window containing ``now`` (Melbourne wall clock, DST-safe via zoneinfo), else None."""
    local = now.astimezone(MELBOURNE)
    minutes = local.hour * 60 + local.minute
    for sh, sm, eh, em in HOLD_WINDOWS:
        if sh * 60 + sm <= minutes <= eh * 60 + em:
            return f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d}"
    return None


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ----------------------------------------------------------------------------- stores with a listing method
# delivery_record's stores can only load one brief; recovery has to discover candidates. These subclasses add
# ``list_recent`` without touching delivery_record.py (an API addition for that module is proposed in the report).

class RecoveryStore(Protocol):
    def claim(self, rec: dr.AttemptRecord) -> None: ...
    def update(self, rec: dr.AttemptRecord) -> None: ...
    def load(self, brief_table: str, brief_id: str, channel: str, content_hash: str | None = None) -> list[dr.AttemptRecord]: ...
    def list_recent(self, since_iso: str) -> list[dr.AttemptRecord]: ...


class InMemoryRecoveryStore(dr.InMemoryAttemptStore):
    """Kept for compatibility: ``list_recent`` is now part of ``delivery_record``'s own stores."""


class PostgrestRecoveryStore(dr.PostgrestAttemptStore):
    """Kept for compatibility: ``list_recent`` is now part of ``delivery_record``'s own stores."""
    LIMIT = 500

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.LIST_LIMIT = self.LIMIT


def postgrest_text_loader(url: str, key: str, timeout: int = 8) -> TextLoader:
    """Stored brief text for ``captains_daily_briefs`` rows (SELECT of ``brief_text``); other tables have none."""
    def _load(brief_table: str, brief_id: str) -> str | None:
        if brief_table != "captains_daily_briefs":
            return None
        q = {"id": f"eq.{brief_id}", "select": "brief_text", "limit": "1"}
        req = urllib.request.Request(f"{url.rstrip('/')}/rest/v1/captains_daily_briefs?{urllib.parse.urlencode(q)}",
                                     headers={"apikey": key, "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - SUPABASE_URL env, https; SELECT only
            rows = json.loads(resp.read())
        return rows[0].get("brief_text") if rows else None
    return _load


# ----------------------------------------------------------------------------- the job

def _empty_report(now: datetime, mode: str) -> dict:
    return {
        "schema": SCHEMA, "kind": KIND, "generated_at": now.astimezone(timezone.utc).isoformat(), "mode": mode,
        "status": "ok", "hold_window": None, "kill_switch": False, "lookback_hours": LOOKBACK_HOURS,
        "counts": {"briefs": 0, "confirmed": 0, "needs_attention": 0, "due_authorised_resend": 0, "due_continue": 0,
                   "in_flight_wait": 0, "recovered_interrupted": 0, "expired": 0, "refused": 0, "sent": 0},
        "preventable_duplicates": 0, "needs_attention": False, "items": [], "errors": [],
        "exactly_once_claimed": False,
    }


def _short_error(exc: BaseException) -> str:
    return type(exc).__name__


def _default_ledger():
    try:
        from intelligence import delivery_degraded as dd
        return dd.DegradedLedger()
    except Exception:  # noqa: BLE001
        return None


def _ledger_hold(ledger, table: str, brief_id: str, attempts: list) -> str | None:
    """A local-ledger entry for this brief that the store does not yet hold (or a row that is stale against it) means the stored attempts may
    understate what was sent. Plan and send nothing for it until it is imported (a resend now could duplicate chunks)."""
    if ledger is None:
        return None
    try:
        for chash in {a.content_hash for a in attempts}:
            e = ledger.get(ledger.key(table, brief_id, chash))
            if e and not e.get("imported") and (e.get("needs_update") or e.get("state") in ("finished", "started")):
                return "local ledger holds a newer state for this brief that is not in the attempt store yet"
    except Exception:  # noqa: BLE001
        return None
    return None


def run_recovery(*, store: RecoveryStore, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 apply: bool | None = None, text_loader: TextLoader | None = None,
                 send_chunk: dr.SendChunk | None = None, split: dr.Splitter | None = None,
                 env=None, ledger=None) -> dict:
    """One recovery pass. ``apply`` can only DISABLE apply (False); enabling comes from the flags alone.
    Returns the structured report; never raises for store or send problems (they are recorded in ``errors``)."""
    now = clock()
    do_apply = apply is not False and apply_enabled(env)
    report = _empty_report(now, "apply" if do_apply else "report_only")
    if kill_switch_on(env):
        report.update(status="disabled", kill_switch=True)
        return report
    held = hold_window(now)
    if held:
        report.update(status="held", hold_window=held)
        return report
    try:
        recent = store.list_recent((now - timedelta(hours=LOOKBACK_HOURS)).astimezone(timezone.utc).isoformat())
    except Exception as exc:  # noqa: BLE001 - fail safe: an unreadable store means no decision and no send
        report["status"] = "error"
        report["errors"].append(f"list_recent:{_short_error(exc)}")
        report["needs_attention"] = True
        return report

    briefs: dict[tuple, list[dr.AttemptRecord]] = {}
    for a in recent:
        briefs.setdefault((a.brief_table, a.brief_id, a.channel), []).append(a)
    c = report["counts"]
    sends = 0
    stop_sending = False

    ledger = ledger if ledger is not None else _default_ledger()
    if do_apply and ledger is not None:        # apply what this host already knows (final states the store never received) before judging any row
        try:
            from intelligence import delivery_degraded as _dd
            _dd.import_ledger(store, ledger)
        except Exception as exc:  # noqa: BLE001 - the per-brief ledger hold below still protects against acting on a stale row
            report["errors"].append(f"import_ledger:{_short_error(exc)}")

    for (table, brief_id, channel), attempts in sorted(briefs.items()):
        c["briefs"] += 1
        base = {"brief_table": table, "brief_id": brief_id, "channel": channel}
        held = _ledger_hold(ledger, table, brief_id, attempts)
        if held:
            c["needs_attention"] += 1
            report["needs_attention"] = True
            report["items"].append({**base, "action": "ledger_pending_import", "detail": held})
            continue
        # --- interrupted attempts: only after a grace period, and never if any attempt of this brief may be live
        in_flight = [a for a in attempts if a.state != "finished"]
        fresh = [a for a in in_flight if (_parse(a.started_at) or now) > now - timedelta(minutes=STALE_INTERRUPTED_MINUTES)]
        if fresh:
            c["in_flight_wait"] += 1
            report["items"].append({**base, "action": "in_flight_wait", "attempts": len(attempts)})
            continue
        recovered = 0
        if in_flight:
            recovered = len(in_flight)
            try:
                if do_apply:
                    dr.recover_interrupted(table, brief_id, channel, store)
                    attempts = store.load(table, brief_id, channel)
                else:                                   # projection on a throwaway copy: no store write in report-only
                    sim = dr.InMemoryAttemptStore([copy.deepcopy(a.to_row()) for a in attempts])
                    dr.recover_interrupted(table, brief_id, channel, sim)
                    attempts = sim.load(table, brief_id, channel)
                c["recovered_interrupted"] += recovered if do_apply else 0
            except Exception as exc:  # noqa: BLE001
                report["errors"].append(f"recover_interrupted:{brief_id}:{_short_error(exc)}")
                report["items"].append({**base, "action": "error", "detail": "recover_interrupted_failed"})
                report["needs_attention"] = True
                continue
        for chash in sorted({a.content_hash for a in attempts}):
            group = [a for a in attempts if a.content_hash == chash]
            item = _plan_item(base, chash, group, recovered, now, do_apply)
            report["preventable_duplicates"] += item.pop("_preventable", 0)
            action = item["action"]
            if action == "confirmed":
                c["confirmed"] += 1
            else:
                c["needs_attention"] += 1
                report["needs_attention"] = True
                key = {"authorised_resend_due": "due_authorised_resend", "continue_due": "due_continue",
                       "expired": "expired", "refused": "refused", "waiting": None}.get(action)
                if key:
                    c[key] += 1
            if do_apply and action in ("authorised_resend_due", "continue_due"):
                if stop_sending or sends >= MAX_SENDS_PER_RUN:
                    item["apply_result"] = "deferred_run_limit"
                else:
                    item["apply_result"], sent, halt = _apply_one(store, table, brief_id, channel, chash, group, item, text_loader,
                                                                  send_chunk, split, clock, env)
                    sends += 1 if sent else 0
                    stop_sending = stop_sending or halt
                    c["sent"] += 1 if sent else 0
            item.pop("_kind", None)
            report["items"].append(item)
    return report


def _plan_item(base: dict, chash: str, group: list[dr.AttemptRecord], recovered: int, now: datetime, do_apply: bool) -> dict:
    roll = dr.rollup(group)
    item = {**base, "content_hash": chash[:12], "attempts": len(group), "outcome": roll.outcome.value if roll else None,
            "confirmed_chunks": roll.confirmed_chunks if roll else [], "ambiguous_chunks": roll.ambiguous_chunks if roll else [],
            "chunks_total": roll.chunks_total if roll else 0, "would_recover_interrupted": recovered if not do_apply else 0,
            "recovery_resends": roll.recovery_resends if roll else 0, "disclosure": roll.disclosure if roll else None,
            "_preventable": dr.duplicate_report(group)["preventable_duplicates"]}
    if roll is None or roll.outcome is dr.DeliveryOutcome.CONFIRMED:
        item["action"] = "confirmed"
        return item
    plan = dr.plan_recovery(group)
    item["plan_reason"] = plan.reason
    first = min((_parse(a.started_at) or now) for a in group)
    last_activity = max(_last_real_activity(a, now) for a in group)
    if not plan.allowed:
        item["action"] = "refused"
        item["preventable_duplicate_prevented"] = plan.preventable_duplicate
        return item
    if now - first > timedelta(hours=MAX_RECOVERY_AGE_HOURS):
        item["action"] = "expired"
        item["detail"] = f"older than {MAX_RECOVERY_AGE_HOURS}h: reported, not resent"
        return item
    resend = plan.reason == "ambiguous_prior_attempt"
    item["action"] = "authorised_resend_due" if resend else "continue_due"
    item["chunk_indexes"] = plan.chunk_indexes
    item["_kind"] = (dr.AttemptKind.AUTHORISED_RECOVERY_RESEND if resend else dr.AttemptKind.PRIMARY).value
    if resend and now - last_activity < timedelta(minutes=MIN_AMBIGUITY_AGE_MINUTES):
        item["not_before"] = (last_activity + timedelta(minutes=MIN_AMBIGUITY_AGE_MINUTES)).astimezone(timezone.utc).isoformat()
    return item


def _last_real_activity(a: dr.AttemptRecord, now: datetime) -> datetime:
    """When the attempt last really did something. The chunk and finish stamps that ``recover_interrupted`` writes
    describe the recovery, not the send, so they are ignored (otherwise recovery would restart the waiting period)."""
    stamps = [_parse(a.started_at)] + [_parse(c.at) for c in a.chunks if c.error != "interrupted_in_flight"]
    if "recovered_after_restart" not in (a.reason or ""):
        stamps.append(_parse(a.finished_at))
    return max((t for t in stamps if t), default=now)


def _apply_one(store, table, brief_id, channel, chash, group, item, text_loader, send_chunk, split, clock, env):
    """Returns (result, sent, halt). ``halt`` stops any further sending in this run (store/transport trouble)."""
    if kill_switch_on(env):
        return "skipped_kill_switch", False, True
    if hold_window(clock()):
        return "skipped_hold_window", False, True
    if item.get("not_before") and clock().astimezone(timezone.utc).isoformat() < item["not_before"]:
        return "waiting_ambiguity_age", False, False
    if text_loader is None:
        return "skipped_no_text_loader", False, False
    try:
        text = text_loader(table, brief_id)
    except Exception as exc:  # noqa: BLE001
        return f"skipped_text_load_failed:{_short_error(exc)}", False, False
    if not text or dr.content_hash(text) != chash:
        return "skipped_content_unavailable_or_changed", False, False
    if send_chunk is None or split is None:
        from intelligence import delivery_adapter as da
        send_chunk = send_chunk or da.make_telegram_sender()
        split = split or da.split_for_telegram
    if kill_switch_on(env):                     # last look before anything is written or sent
        return "skipped_kill_switch", False, True
    if hold_window(clock()):
        return "skipped_hold_window", False, True
    kind = dr.AttemptKind(item["_kind"])
    try:
        res = dr.deliver(table, brief_id, text, channel=channel, store=store, split=split, send_chunk=send_chunk, kind=kind,
                         authorised_by=dr.POLICY_AUTHORISER if kind is dr.AttemptKind.AUTHORISED_RECOVERY_RESEND else None)
    except Exception as exc:  # noqa: BLE001 - after an error mid-send the state is unknown: stop the run, the next pass reads the records
        return f"error:{_short_error(exc)}", False, True
    if res.refused_reason:
        return f"refused:{res.refused_reason}", False, False
    return f"sent:{res.outcome.value if res.outcome else 'unknown'}", True, False


# ----------------------------------------------------------------------------- output and scheduler entry point

def emit_report(report: dict, path: str | None = None) -> None:
    """One log line (always) and, when a path is configured, an atomically replaced JSON file for the deadman."""
    log.info("[delivery_recovery_report] %s", json.dumps(report, sort_keys=True, default=str))
    path = path or os.environ.get(REPORT_PATH_ENV)
    if not path:
        return
    try:
        d = os.path.dirname(path) or "."
        fd, tmp = tempfile.mkstemp(prefix=".recovery-report-", dir=d)
        with os.fdopen(fd, "w") as fh:
            json.dump(report, fh, sort_keys=True, default=str)
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("[delivery_recovery_report] could not write %s: %s", path, _short_error(exc))


def job_recovery() -> dict | None:
    """Scheduler entry point (same shape as ``intel_products_job.job_daily``): never raises. Report-only unless the
    apply flags are on. Not registered by this change."""
    try:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            report = _empty_report(datetime.now(timezone.utc), "report_only")
            report.update(status="error", errors=["supabase_not_configured"], needs_attention=True)
        else:
            report = run_recovery(store=PostgrestRecoveryStore(url, key), text_loader=postgrest_text_loader(url, key))
        emit_report(report)
        return report
    except Exception as exc:  # noqa: BLE001 - scheduled job must never take the scheduler down; logged
        log.error("[delivery_recovery] job failed: %s", _short_error(exc))
        return None
