"""Bounded degraded-delivery path for briefs when the delivery AUDIT store misbehaves (flag ``BRIEF_DELIVERY_RECORD_V1`` callers only).

Principle: a failure of the audit store must never silently stop a valid brief reaching the Captain, and must never be hidden either.
``delivery_record.deliver`` claims an attempt row before it sends; if the store raised there, the brief used to be dropped (fail closed on
the audit trail while the legacy path fails open). This module wraps ``deliver`` so that:

* store unavailable BEFORE the send (``load`` or ``claim`` raises, or no store could be built): the brief is sent once through the same
  per-chunk classified sender, with a short uncertainty footer, and the outcome is written to a LOCAL LEDGER (atomic JSON file). The
  ledger is the duplicate-risk control: a later attempt for the same brief+content is refused unless every earlier degraded chunk was
  definitely not delivered. Each chunk is sent at most once (no blind retry; the adapter's single definite-failure retry only).
  Unlike the recorded path a definite or ambiguous failure of one chunk does not stop the later chunks (content reaching the Captain
  matters more than strict stop-at-first-failure, and sending later chunks creates no duplicate).
* store fails AFTER the claim (an ``update`` raises while chunks are being sent): sending continues, the state is kept in memory, a final
  re-sync is tried a bounded number of times, and anything that still cannot be written is put in the ledger so it can be imported later.
* the local ledger is consulted on EVERY send path before anything is claimed or sent (``_ledger_gate``): an entry the store does not know about
  is imported first; one that cannot be imported and may have been delivered refuses the send. Its default location is persistent and per-user
  (``$XDG_STATE_HOME/tjrhq/brief-degraded-ledger.json``, else ``~/.local/state/...``; override ``BRIEF_DEGRADED_LEDGER``), 0600 in a 0700 directory,
  and it only blocks and records: it holds no message text and has no way to send.
* a process interruption (``BaseException`` out of the sender) after the claim finalises the attempt as UNKNOWN (never left 'sending')
  where the process is still able to run code; a hard kill cannot, which is what ``recover_pending`` is for.
* every degraded event emits ONE structured alert (a JSON log line with a stable prefix, also appended to the ledger) that the Production
  Operations deadman can consume. This module changes no scheduling and calls no platform alert path.

What this does NOT do: it does not claim exactly-once, does not make Telegram able to confirm an ambiguous send, and it cannot recover by
itself. ``recover_pending`` and ``import_ledger`` have to be CALLED by something (a startup hook or a periodic job): that is a Production
Operations dependency recorded in the Batch 1 logic engineering report.

Also here, because ``delivery_record.py`` is owned by another work package: validation of ``authorised_by`` against a fixed enumerated set
(callers use ``deliver_resilient``, which enforces it) and a recovery marker that is sent merged into the first resent chunk, so the
Captain never sees "resent" without content.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from intelligence import delivery_record as dr

log = logging.getLogger("brief-delivery-degraded")

ALERT_PREFIX = "[brief-delivery-degraded]"
ALERT_EVENT = "BRIEF_DELIVERY_AUDIT_DEGRADED"
LEDGER_ENV = "BRIEF_DEGRADED_LEDGER"
LEDGER_DEFAULT_RELATIVE = os.path.join("tjrhq", "brief-degraded-ledger.json")
STARTED_STALE_SECONDS = 300.0


def default_ledger_path() -> str:
    """Persistent, per-user default: ``$XDG_STATE_HOME/tjrhq/brief-degraded-ledger.json`` (else ``~/.local/state/...``). Not tmpfs, not a
    shared or world-writable directory, so it survives a reboot and cannot be pre-created by another local user. Override with
    ``BRIEF_DEGRADED_LEDGER`` (a file path)."""
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, LEDGER_DEFAULT_RELATIVE)
MAX_LEDGER_ENTRIES = 400
MAX_ALERTS = 100
RESYNC_ATTEMPTS = 3
TELEGRAM_LIMIT = 4096

POLICY_AUTHORISER = dr.POLICY_AUTHORISER
AUTHORISERS = dr.AUTHORISERS
UNCERTAINTY_FOOTER = "\n\n<i>Delivery audit record unavailable for this brief. If it appears twice, one earlier send was unconfirmed.</i>"


def valid_authoriser(authorised_by: str | None) -> bool:
    return authorised_by in AUTHORISERS


class StoreDown(Exception):
    """The attempt store could not be used before anything was sent."""

    def __init__(self, phase: str, cause: BaseException | None = None):
        super().__init__(f"{phase}:{type(cause).__name__ if cause else ''}")
        self.phase = phase
        self.cause = cause


# ----------------------------------------------------------------------------- local ledger

class DegradedLedger:
    """Atomic JSON file of degraded deliveries and alerts. Falls back to memory when the file cannot be written or cannot be trusted (and says so).

    The ledger is a BLOCKING and RECORDING device only: it holds no message text, never calls a sender and offers no way to send. It is consulted
    before a send to refuse a duplicate and written after one to remember what happened; nothing it contains can cause a message to be sent.
    The file is created 0600 in a 0700 directory owned by the running user; a file owned by someone else, or one this user cannot make private,
    is not trusted (memory only, ``trusted`` False)."""

    def __init__(self, path: str | None = None):
        self.path = path or os.environ.get(LEDGER_ENV) or default_ledger_path()
        self._lock = threading.Lock()
        self._mem: dict | None = None
        self.persistent = True
        self.trusted = True

    def _path_trusted(self) -> bool:
        """Owner is this user and the file/directory are not group- or world-writable (tightened when this user owns them)."""
        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        if hasattr(os, "getuid") and st.st_uid != os.getuid():
            return False
        if st.st_mode & 0o077:
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                return False
        return True

    def permissions(self) -> dict:
        """For health checks and tests: the octal modes of the file and its directory (None when absent)."""
        out: dict = {"path": self.path, "file_mode": None, "dir_mode": None, "trusted": self.trusted, "persistent": self.persistent}
        try:
            out["file_mode"] = oct(os.stat(self.path).st_mode & 0o777)
        except OSError:
            pass
        try:
            out["dir_mode"] = oct(os.stat(os.path.dirname(self.path) or ".").st_mode & 0o777)
        except OSError:
            pass
        return out

    def _read(self) -> dict:
        if self._mem is not None:
            return self._mem
        if not self._path_trusted():
            log.warning("%s ledger file is not trusted (owner or permissions): memory only", ALERT_PREFIX)
            self.trusted = False
            self.persistent = False
            self._mem = {"entries": {}, "alerts": []}
            return self._mem
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data.setdefault("entries", {})
                data.setdefault("alerts", [])
                return data
        except FileNotFoundError:
            pass
        except Exception as exc:  # noqa: BLE001 - unreadable ledger: treat as empty but say so
            log.warning("%s ledger unreadable (%s)", ALERT_PREFIX, type(exc).__name__)
        return {"entries": {}, "alerts": []}

    def _write(self, data: dict) -> None:
        if self._mem is not None:
            self._mem = data
            return
        try:
            d = os.path.dirname(self.path) or "."
            os.makedirs(d, mode=0o700, exist_ok=True)
            if hasattr(os, "getuid") and os.stat(d).st_uid == os.getuid() and os.stat(d).st_mode & 0o077:
                os.chmod(d, 0o700)
            fd, tmp = tempfile.mkstemp(prefix=".ledger-", dir=d)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except Exception as exc:  # noqa: BLE001 - the ledger is best-effort durable; fall back to memory for this process
            log.warning("%s ledger not writable (%s): memory only", ALERT_PREFIX, type(exc).__name__)
            self.persistent = False
            self._mem = data

    @staticmethod
    def key(table: str, ref: str, content_hash: str) -> str:
        return f"{table}:{ref}:{content_hash}"

    def get(self, key: str) -> dict | None:
        with self._lock:
            return (self._read().get("entries") or {}).get(key)

    def put(self, key: str, entry: dict) -> None:
        with self._lock:
            data = self._read()
            data["entries"][key] = entry
            if len(data["entries"]) > MAX_LEDGER_ENTRIES:
                done = sorted((k for k, v in data["entries"].items() if v.get("state") == "finished" and v.get("imported")),
                              key=lambda k: data["entries"][k].get("started_at", ""))
                for k in done[: len(data["entries"]) - MAX_LEDGER_ENTRIES]:
                    data["entries"].pop(k, None)
            self._write(data)

    def add_alert(self, alert: dict) -> None:
        with self._lock:
            data = self._read()
            data["alerts"] = (data.get("alerts") or [])[-(MAX_ALERTS - 1):] + [alert]
            self._write(data)

    def entries(self) -> dict:
        with self._lock:
            return dict(self._read().get("entries") or {})


def emit_alert(alert: dict, ledger: DegradedLedger | None = None) -> dict:
    """ONE structured alert: a JSON log line with a stable prefix (consumable by the Production Operations deadman) plus a ledger record."""
    alert = {"event": ALERT_EVENT, "ts": dr.utcnow(), **alert}
    log.error("%s %s", ALERT_PREFIX, json.dumps(alert, sort_keys=True, default=str))
    if ledger is not None:
        try:
            ledger.add_alert(alert)
        except Exception:  # noqa: BLE001, S110 - the log line above is the alert of record
            pass
    return alert


# ----------------------------------------------------------------------------- store guard and marker handling

class GuardedStore:
    """Wraps an attempt store for ``dr.deliver``: ``load``/``claim`` failures become ``StoreDown`` (nothing sent yet); ``update`` failures after the
    claim are absorbed (sending continues) and counted."""

    def __init__(self, inner):
        self.inner = inner
        self.current: dr.AttemptRecord | None = None
        self.update_failures = 0
        self.last_error: BaseException | None = None
        self.prior: list[dr.AttemptRecord] | None = None      # what the store held BEFORE this send (the first load)

    def load(self, brief_table, brief_id, channel, content_hash=None):
        try:
            out = self.inner.load(brief_table, brief_id, channel, content_hash)
        except Exception as exc:
            raise StoreDown("load", exc) from exc
        if self.prior is None:
            self.prior = list(out)
        return out

    def list_recent(self, since_iso):
        return self.inner.list_recent(since_iso)

    def claim(self, rec):
        try:
            self.inner.claim(rec)
        except dr.AttemptConflict:
            raise
        except Exception as exc:
            raise StoreDown("claim", exc) from exc
        self.current = rec

    def update(self, rec):
        self.current = rec
        try:
            self.inner.update(rec)
        except Exception as exc:  # noqa: BLE001 - absorbed: the brief must still be sent
            self.update_failures += 1
            self.last_error = exc

    def resync(self, attempts: int = RESYNC_ATTEMPTS) -> bool:
        """Final bounded attempts to write the current record; True when written."""
        if self.current is None:
            return True
        for _ in range(attempts):
            try:
                self.inner.update(self.current)
                return True
            except Exception as exc:  # noqa: BLE001
                self.last_error = exc
        return False


def _deferred_marker_sender(send_chunk: Callable[[str], dr.ChunkResult]) -> Callable[[str], dr.ChunkResult]:
    """The recovery marker is merged into the first resent chunk instead of being sent on its own first, so a resend whose first content
    chunk is rejected or ambiguous never leaves the Captain with a 'resent' notice and no content. If the merged text would exceed the
    Telegram limit the marker is sent immediately before that chunk (never before knowing a content send is about to happen)."""
    state = {"pending": False}

    def _send(piece: str) -> dr.ChunkResult:
        if piece == dr.RECOVERY_MARKER:
            state["pending"] = True
            return dr.ChunkResult(-1, dr.CHUNK_CONFIRMED, error="marker_merged_into_first_resent_chunk", attempts=0, at=dr.utcnow())
        if state["pending"]:
            state["pending"] = False
            merged = f"{dr.RECOVERY_MARKER}\n\n{piece}"
            if len(merged) <= TELEGRAM_LIMIT:
                res = send_chunk(merged)
                res.chunk_hash = dr.content_hash(piece)          # the record stays about the content chunk
                return res
            send_chunk(dr.RECOVERY_MARKER)                         # oversize: marker immediately before the content send
        return send_chunk(piece)

    return _send


# ----------------------------------------------------------------------------- results

@dataclass
class ResilientResult:
    roll: dr.Rollup | None
    degraded: bool = False
    phase: str | None = None
    recorded: bool = True
    refused_reason: str | None = None
    alert: dict | None = None
    result: dr.DeliveryResult | None = None
    disclosure: str | None = None
    preventable_duplicate_prevented: bool = False

    @property
    def outcome(self) -> dr.DeliveryOutcome | None:
        return self.roll.outcome if self.roll else None


def _with_footer(text: str) -> str:
    return text if text.endswith(UNCERTAINTY_FOOTER) else text + UNCERTAINTY_FOOTER


def _entry_chunks(chunks: list[dr.ChunkResult]) -> list[dict]:
    return [{"index": c.index, "state": c.state, "message_id": c.message_id, "error": c.error, "chunk_hash": c.chunk_hash, "at": c.at}
            for c in chunks]


def _definitely_undelivered(entry: dict) -> bool:
    chunks = entry.get("chunks") or []
    return entry.get("state") == "finished" and bool(chunks) and all(c.get("state") in (dr.CHUNK_FAILED, dr.CHUNK_NOT_ATTEMPTED) for c in chunks)


def _send_piece(send_chunk, piece: str, index: int) -> dr.ChunkResult:
    try:
        res = send_chunk(piece)
    except Exception as exc:  # noqa: BLE001 - a raising sender may have written the request: ambiguous, never success
        res = dr.ChunkResult(index, dr.CHUNK_UNKNOWN, error=type(exc).__name__, attempts=1)
    res.index = index
    res.chunk_hash = res.chunk_hash or dr.content_hash(piece)
    res.at = res.at or dr.utcnow()
    return res


def _degraded_send(table: str, ref: str, text: str, *, channel: str, split, send_chunk, brief_type: str, ledger: DegradedLedger,
                   phase: str, cause: BaseException | None, store) -> ResilientResult:
    """Store unusable BEFORE anything was sent: bounded single send, ledger as the duplicate control, one alert."""
    h = dr.content_hash(text)
    key = ledger.key(table, ref, h)
    prior = ledger.get(key)
    base_alert = {"brief_type": brief_type, "brief_table": table, "brief_ref": ref, "phase": phase,
                  "store_error": type(cause).__name__ if cause else None, "ledger_persistent": ledger.persistent}
    if prior and not _definitely_undelivered(prior):
        alert = emit_alert({**base_alert, "outcome": "REFUSED", "duplicate_risk": "blocked",
                            "detail": "an earlier degraded send for this brief is not known to be undelivered; not sent again"}, ledger)
        return ResilientResult(None, degraded=True, phase=phase, recorded=False, refused_reason="degraded_duplicate_risk_blocked",
                               alert=alert, preventable_duplicate_prevented=True,
                               disclosure="UNRECORDED: earlier degraded send for this brief is unconfirmed; no second send was made")
    entry = {"key": key, "attempt_id": str(uuid.uuid4()), "state": "started", "started_at": dr.utcnow(), "table": table, "ref": ref,
             "channel": channel, "content_hash": h, "brief_type": brief_type, "phase": phase, "chunks": [], "imported": False}
    pieces = split(_with_footer(text))
    entry["chunks_total"] = len(pieces)
    ledger.put(key, entry)                                    # persisted BEFORE the first send: a crash leaves 'started' = unknown
    results: list[dr.ChunkResult] = []
    for i, piece in enumerate(pieces):
        results.append(_send_piece(send_chunk, piece, i))
        entry["chunks"] = _entry_chunks(results)
        ledger.put(key, entry)
    outcome = dr.outcome_from_chunks(results, len(pieces))
    rec = dr.AttemptRecord(table, ref, channel, h, attempt_no=1, chunks_total=len(pieces), chunks=results, state="finished", outcome=outcome,
                           reason=f"degraded_store_unavailable:{phase}", finished_at=dr.utcnow())
    roll = dr.rollup([rec])
    recorded = False
    if store is not None:                                     # one best-effort write in case the store has come back
        try:
            store.claim(rec)
            recorded = True
        except Exception:  # noqa: BLE001
            recorded = False
    entry.update({"state": "finished", "outcome": outcome.value, "finished_at": dr.utcnow(), "imported": recorded, "record": rec.to_row()})
    ledger.put(key, entry)
    disclosure = (f"UNRECORDED: delivery audit store unavailable ({phase}); sent once via the degraded path, outcome {outcome.value}"
                  + ("; chunk(s) " + str(roll.ambiguous_chunks) + " unconfirmed" if roll and roll.ambiguous_chunks else "")
                  + ("; recorded after the fact" if recorded else "; held in the local ledger until the store recovers")
                  + ". Do not resend blindly: a resend can duplicate.")
    alert = emit_alert({**base_alert, "outcome": outcome.value, "recorded": recorded, "duplicate_risk": "controlled_by_local_ledger",
                        "chunks_total": len(pieces), "confirmed_chunks": roll.confirmed_chunks if roll else [],
                        "ambiguous_chunks": roll.ambiguous_chunks if roll else [], "action": "import_ledger + recover_pending when the store recovers"}, ledger)
    return ResilientResult(roll, degraded=True, phase=phase, recorded=recorded, alert=alert, disclosure=disclosure)


def _finalise_interrupted(guard: GuardedStore, ledger: DegradedLedger, brief_type: str) -> None:
    """A BaseException left the sender after the claim: do not leave the attempt 'sending'. The in-flight chunk is UNKNOWN."""
    rec = guard.current
    if rec is None or rec.state == "finished":
        return
    sent = {c.index for c in rec.chunks if c.index >= 0}
    plan = rec.planned_chunks or list(range(max(rec.chunks_total, 0)))
    pending = [i for i in plan if i not in sent]
    if pending:
        rec.chunks.append(dr.ChunkResult(pending[0], dr.CHUNK_UNKNOWN, error="interrupted_in_flight", at=dr.utcnow()))
        for i in pending[1:]:
            rec.chunks.append(dr.ChunkResult(i, dr.CHUNK_NOT_ATTEMPTED))
    elif not rec.chunks:
        rec.chunks.append(dr.ChunkResult(0, dr.CHUNK_UNKNOWN, error="interrupted_in_flight", at=dr.utcnow()))
    rec.reason = (rec.reason or "") + ";interrupted"
    rec.outcome = dr.attempt_outcome(rec)
    rec.state = "finished"
    rec.finished_at = dr.utcnow()
    written = guard.resync()
    emit_alert({"brief_type": brief_type, "brief_table": rec.brief_table, "brief_ref": rec.brief_id, "phase": "interrupted",
                "outcome": rec.outcome.value, "recorded": written, "duplicate_risk": "recorded_as_unknown",
                "action": "recover_pending then authorised resend if required"}, ledger)
    if not written:
        key = ledger.key(rec.brief_table, rec.brief_id, rec.content_hash)
        ledger.put(key, {"key": key, "state": "finished", "outcome": rec.outcome.value, "started_at": rec.started_at, "table": rec.brief_table,
                         "ref": rec.brief_id, "channel": rec.channel, "content_hash": rec.content_hash, "brief_type": brief_type,
                         "phase": "interrupted", "chunks": _entry_chunks(rec.chunks), "imported": False, "record": rec.to_row(), "needs_update": True})


def _entry_to_record(e: dict) -> dr.AttemptRecord:
    """The attempt record a ledger entry stands for. A 'started' entry that never finished (the process died mid-send) becomes a finished
    attempt whose in-flight chunk is UNKNOWN and whose later chunks were never attempted."""
    if e.get("record"):
        return dr.AttemptRecord.from_row(e["record"])
    chunks = [dr.ChunkResult(c["index"], c["state"], c.get("message_id"), c.get("error"), 1, c.get("chunk_hash"), c.get("at")) for c in (e.get("chunks") or [])]
    total = int(e.get("chunks_total") or max(1, len(chunks) + 1))
    done = {c.index for c in chunks}
    pending = [i for i in range(total) if i not in done]
    if pending:
        chunks.append(dr.ChunkResult(pending[0], dr.CHUNK_UNKNOWN, error="interrupted_in_flight", at=dr.utcnow()))
        chunks += [dr.ChunkResult(i, dr.CHUNK_NOT_ATTEMPTED) for i in pending[1:]]
    rec = dr.AttemptRecord(e["table"], e["ref"], e.get("channel") or "telegram", e["content_hash"], attempt_no=1, chunks_total=total, chunks=chunks,
                           state="finished", reason=f"ledger_entry:{e.get('phase') or 'degraded'};interrupted", started_at=e.get("started_at") or dr.utcnow(),
                           finished_at=dr.utcnow())
    rec.outcome = dr.attempt_outcome(rec)
    return rec


def _stale_started(e: dict, now=None) -> bool:
    from datetime import datetime, timezone
    try:
        t = datetime.fromisoformat(str(e.get("started_at")))
        t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return ((now or datetime.now(timezone.utc)) - t).total_seconds() >= STARTED_STALE_SECONDS


def _ledger_gate(ledger: DegradedLedger, store, table: str, ref: str, text: str, brief_type: str) -> ResilientResult | None:
    """Consulted on EVERY send path before anything is claimed or sent. If the local ledger holds an entry for this brief and content that the store
    does not know about (a send made while the store was down), try to import it first; when it cannot be imported and a chunk may have been
    delivered, refuse: the normal path would otherwise claim in an empty store and send the whole brief a second time. Returns a refusal or None
    (proceed; the store's own policy then applies). Blocks and records only: it never sends."""
    key = ledger.key(table, ref, dr.content_hash(text))
    e = ledger.get(key)
    if not e or e.get("imported"):
        return None
    if store is not None:
        try:
            import_ledger(store, ledger, only_key=key)
        except Exception:  # noqa: BLE001, S110 - store trouble: fall through to the duplicate-risk decision below
            pass
        e = ledger.get(key) or e
        if e.get("imported"):
            return None
    if _definitely_undelivered(e):
        return None
    alert = emit_alert({"brief_type": brief_type, "brief_table": table, "brief_ref": ref, "phase": "ledger_pending_import", "outcome": "REFUSED",
                        "duplicate_risk": "blocked", "ledger_state": e.get("state"),
                        "detail": "an earlier send for this brief is held in the local ledger, is not in the attempt store and may have been delivered; not sent again"}, ledger)
    return ResilientResult(None, degraded=True, phase="ledger_pending_import", recorded=False, refused_reason="ledger_pending_import_duplicate_risk_blocked",
                           alert=alert, preventable_duplicate_prevented=True,
                           disclosure="UNRECORDED: an earlier send for this brief is held in the local ledger and not yet in the attempt store; no second send was made")


def deliver_resilient(table: str, ref: str, text: str, *, channel: str, store, split, send_chunk, brief_type: str = "brief",
                      ledger: DegradedLedger | None = None, kind: dr.AttemptKind = dr.AttemptKind.PRIMARY,
                      authorised_by: str | None = None) -> ResilientResult:
    """``dr.deliver`` that never lets the audit store stop a valid brief and never leaves an attempt 'sending'. See the module docstring."""
    ledger = ledger or DegradedLedger()
    if kind is dr.AttemptKind.AUTHORISED_RECOVERY_RESEND:  # noqa: SIM102 - nested conditions kept for readability
        if not valid_authoriser(authorised_by):
            alert = emit_alert({"brief_type": brief_type, "brief_table": table, "brief_ref": ref, "phase": "authorisation",
                                "outcome": "REFUSED", "detail": "authorised_by is not in the enumerated set"}, ledger)
            return ResilientResult(None, refused_reason="authoriser_not_enumerated", alert=alert, preventable_duplicate_prevented=True)
    gate = _ledger_gate(ledger, store, table, ref, text, brief_type)
    if gate is not None:
        return gate
    if store is None:
        return _degraded_send(table, ref, text, channel=channel, split=split, send_chunk=send_chunk, brief_type=brief_type, ledger=ledger,
                              phase="init", cause=None, store=None)
    guard = GuardedStore(store)
    try:
        res = dr.deliver(table, ref, text, channel=channel, store=guard, split=split, send_chunk=send_chunk, kind=kind, authorised_by=authorised_by)
    except StoreDown as sd:
        if kind is dr.AttemptKind.AUTHORISED_RECOVERY_RESEND:
            alert = emit_alert({"brief_type": brief_type, "brief_table": table, "brief_ref": ref, "phase": sd.phase, "outcome": "REFUSED",
                                "store_error": type(sd.cause).__name__ if sd.cause else None,
                                "detail": "a recovery resend needs the attempt store (it is the duplicate control); not sent"}, ledger)
            return ResilientResult(None, degraded=True, phase=sd.phase, recorded=False, refused_reason="resend_needs_store", alert=alert)
        return _degraded_send(table, ref, text, channel=channel, split=split, send_chunk=send_chunk, brief_type=brief_type, ledger=ledger,
                              phase=sd.phase, cause=sd.cause, store=None)
    except BaseException:
        _finalise_interrupted(guard, ledger, brief_type)
        raise
    degraded = guard.update_failures > 0
    recorded = True
    alert = None
    if degraded:
        recorded = guard.resync()
        phase = "update"
        if not recorded and guard.current is not None:
            rec = guard.current
            key = ledger.key(rec.brief_table, rec.brief_id, rec.content_hash)
            ledger.put(key, {"key": key, "state": rec.state, "outcome": rec.outcome.value if rec.outcome else None, "started_at": rec.started_at,
                             "table": rec.brief_table, "ref": rec.brief_id, "channel": rec.channel, "content_hash": rec.content_hash,
                             "brief_type": brief_type, "phase": phase, "chunks": _entry_chunks(rec.chunks), "imported": False,
                             "record": rec.to_row(), "needs_update": True})
        alert = emit_alert({"brief_type": brief_type, "brief_table": table, "brief_ref": ref, "phase": phase,
                            "store_error": type(guard.last_error).__name__ if guard.last_error else None,
                            "outcome": res.outcome.value if res.outcome else None, "recorded": recorded,
                            "update_failures": guard.update_failures, "duplicate_risk": "recorded_in_memory_and_ledger" if not recorded else "none",
                            "action": "import_ledger when the store recovers" if not recorded else "none"}, ledger)
    roll = res.rollup
    if roll is None and res.attempt is not None:
        roll = dr.rollup([res.attempt])
    if degraded and res.attempt is not None:
        # The store failed while sending, so the rollup read back from it is STALE (it still shows the row as 'sending' with the first chunk
        # only). What this process observed is the truth about what was sent: roll up the attempts held before the send plus the in-memory attempt.
        before = [a for a in (guard.prior or []) if a.attempt_id != res.attempt.attempt_id]
        roll = dr.rollup(before + [res.attempt])
    disclosure = None
    if degraded:
        disclosure = ("UNRECORDED: " if not recorded else "") + (f"delivery audit store failed during the send ({guard.update_failures} write(s)); "
                                                                 + ("final state written after retry" if recorded else "final state held in the local ledger"))
    return ResilientResult(roll, degraded=degraded, phase="update" if degraded else None, recorded=recorded, refused_reason=res.refused_reason,
                           alert=alert, result=res, disclosure=disclosure, preventable_duplicate_prevented=res.preventable_duplicate_prevented)


# ----------------------------------------------------------------------------- recovery (must be CALLED by something: see docstring)

def find_in_flight(store) -> list[dr.AttemptRecord]:
    """Attempts still 'sending'. In-memory stores are scanned; the PostgREST store is queried with a read-only GET."""
    if hasattr(store, "snapshot"):
        return [dr.AttemptRecord.from_row(r) for r in store.snapshot() if r.get("state") != "finished"]
    if isinstance(store, dr.PostgrestAttemptStore):
        import urllib.request
        req = urllib.request.Request(f"{store.url}/rest/v1/{dr.TABLE}?state=eq.sending&order=started_at.asc&limit=200",
                                     headers=store._headers("return=representation"))
        with urllib.request.urlopen(req, timeout=store.timeout) as resp:  # nosec B310 - SUPABASE_URL env, https
            return [dr.AttemptRecord.from_row(r) for r in json.loads(resp.read())]
    return []


@dataclass
class RecoveryItem:
    brief_table: str
    brief_id: str
    channel: str
    attempt_id: str
    action: str                     # 'recovered' | 'recent_left_alone' | 'held_ledger_pending_import'
    outcome: str | None = None
    resend_allowed: bool = False
    resend_reason: str = ""
    chunk_indexes: list[int] = field(default_factory=list)


def recover_pending(store, *, stale_after_seconds: float = 300.0, now_iso: str | None = None, ledger: DegradedLedger | None = None,
                    brief_type: str = "brief") -> list[RecoveryItem]:
    """For attempts left 'sending' longer than ``stale_after_seconds`` (a hard kill): finish them via ``dr.recover_interrupted`` (the in-flight chunk
    becomes UNKNOWN) and report whether an authorised resend is allowed. Sends NOTHING. Emits an alert per recovered attempt."""
    from datetime import datetime, timezone
    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
    out: list[RecoveryItem] = []
    seen: set[tuple[str, str, str]] = set()
    ledger = ledger or DegradedLedger()
    try:                                  # first apply what this host already knows (final states the store never received): a 'sending' row may be stale
        import_ledger(store, ledger)
    except Exception:  # noqa: BLE001, S110 - the in-flight check below still holds back anything the ledger knows about
        pass
    for a in find_in_flight(store):
        le = ledger.get(ledger.key(a.brief_table, a.brief_id, a.content_hash))
        if le and not le.get("imported") and (le.get("needs_update") or le.get("state") == "finished"):
            out.append(RecoveryItem(a.brief_table, a.brief_id, a.channel, a.attempt_id, "held_ledger_pending_import"))
            continue
        try:
            started = datetime.fromisoformat(a.started_at)
        except ValueError:
            started = now
        if (now - started).total_seconds() < stale_after_seconds:
            out.append(RecoveryItem(a.brief_table, a.brief_id, a.channel, a.attempt_id, "recent_left_alone"))
            continue
        k = (a.brief_table, a.brief_id, a.channel)
        if k in seen:
            continue
        seen.add(k)
        fixed = dr.recover_interrupted(a.brief_table, a.brief_id, a.channel, store)
        attempts = store.load(a.brief_table, a.brief_id, a.channel)
        plan = dr.plan_recovery(attempts, authorised_by=POLICY_AUTHORISER)
        roll = dr.rollup(attempts)
        for f in fixed:
            out.append(RecoveryItem(f.brief_table, f.brief_id, f.channel, f.attempt_id, "recovered", roll.outcome.value if roll else None,
                                    plan.allowed, plan.reason, list(plan.chunk_indexes or [])))
            emit_alert({"brief_type": brief_type, "brief_table": f.brief_table, "brief_ref": f.brief_id, "phase": "recovered_after_interruption",
                        "outcome": roll.outcome.value if roll else None, "recorded": True, "resend_allowed": plan.allowed,
                        "duplicate_risk": "resend_may_duplicate_chunks" if plan.allowed else "none",
                        "action": "authorised resend (marked) if the Captain did not receive the brief"}, ledger)
    return out


def import_ledger(store, ledger: DegradedLedger | None = None, *, only_key: str | None = None) -> dict:
    """Push ledger entries the store never saw (degraded sends, failed final updates, sends interrupted mid-way) into the store once it is back,
    so the normal duplicate policy applies to them from then on. ``only_key`` limits it to one entry. Returns counts. Writes only to the attempt
    store; sends nothing."""
    ledger = ledger or DegradedLedger()
    done = failed = skipped = 0
    for key, e in ledger.entries().items():
        if only_key is not None and key != only_key:
            continue
        if e.get("imported") or (e.get("state") != "finished" and not (e.get("state") == "started" and _stale_started(e))):
            skipped += 1
            continue
        if e.get("state") == "finished" and not e.get("record"):
            skipped += 1
            continue
        try:
            rec = _entry_to_record(e)
            if e.get("needs_update"):
                store.update(rec)
            else:
                try:
                    store.claim(rec)
                except dr.AttemptConflict:
                    store.update(rec)
            e["imported"] = True
            ledger.put(key, e)
            done += 1
        except Exception as exc:  # noqa: BLE001 - leave it for the next pass
            failed += 1
            log.warning("%s ledger import failed for %s (%s)", ALERT_PREFIX, key, type(exc).__name__)
    return {"imported": done, "failed": failed, "skipped": skipped}
