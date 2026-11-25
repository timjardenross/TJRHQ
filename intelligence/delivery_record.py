"""Durable, attempt-level delivery records for briefs, and the duplicate/recovery policy.

Design (no exactly-once claim)
------------------------------
* One row per ATTEMPT (not per brief): kind PRIMARY or AUTHORISED_RECOVERY_RESEND, per-chunk results, outcome.
* The attempt row is written BEFORE the first chunk is sent ("claim first") and updated after every chunk, so a
  crash mid-send leaves persisted state. The store enforces the same uniqueness the SQL draft enforces, so two
  concurrent senders cannot both claim a primary for the same (brief, channel, content): this PREVENTS the
  preventable duplicates; it does not make delivery exactly-once.
* Outcomes: CONFIRMED (every chunk accepted with provider evidence), PARTIAL (some chunks confirmed, some not),
  FAILED (provider definitely rejected / never reached, nothing delivered), UNKNOWN (ambiguous right now, e.g.
  timeout after the request was written), UNCONFIRMED (ambiguity remained after a reconciliation pass; the
  Telegram Bot API cannot list sent messages, so reconciliation never upgrades to CONFIRMED by itself).
* Duplicate vocabulary.  PREVENTABLE duplicate = primary sent twice, resend with no prior ambiguity, or resend
  of a CONFIRMED chunk: target 0, enforced by ``authorise_attempt`` and measured by ``duplicate_report``.
  AUTHORISED RECOVERY RESEND = one marked resend of the not-confirmed chunks after ambiguity: it may produce a
  duplicate the Captain can see; it is counted and disclosed separately and is NOT a preventable duplicate.

* Append-only outcome history. A stored attempt is never blind-upserted: ``update`` is a conditional write (the row must
  still be in the state this process last read), and the same transition rules are enforced by a database trigger
  (migration draft 0264): no DELETE, a finished attempt only moves FORWARD (UNKNOWN -> UNCONFIRMED/PARTIAL/CONFIRMED,
  UNCONFIRMED -> PARTIAL/CONFIRMED, PARTIAL -> CONFIRMED), a CONFIRMED attempt and a CONFIRMED chunk never change. A stale
  writer therefore gets AttemptConflict instead of overwriting newer evidence.

Flag: BRIEF_DELIVERY_RECORD_V1 (default OFF) gates the callers. This module sends nothing itself: the caller
supplies ``send_chunk``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

log = logging.getLogger(__name__)

FLAG = "BRIEF_DELIVERY_RECORD_V1"
AUTO_RESEND_FLAG = "BRIEF_DELIVERY_AUTO_RESEND_V1"
TABLE = "intelligence_delivery_attempts"
RECOVERY_MARKER = "Earlier delivery unconfirmed — resent"
POLICY_AUTHORISER = "policy:ambiguous-send-one-marked-resend"
# The only identities that may authorise a recovery resend. Enforced inside ``authorise_attempt`` (and therefore ``deliver``), not only in wrappers.
AUTHORISERS = frozenset({POLICY_AUTHORISER, "captain:manual-recovery", "ops:recovery-scheduler"})
TELEGRAM_LIMIT = 4096
_TRUE = ("1", "true", "yes", "on")


def enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in _TRUE


def auto_resend_enabled() -> bool:
    return enabled() and os.getenv(AUTO_RESEND_FLAG, "").strip().lower() in _TRUE


class DeliveryOutcome(str, Enum):
    CONFIRMED = "CONFIRMED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    UNCONFIRMED = "UNCONFIRMED"


class AttemptKind(str, Enum):
    PRIMARY = "PRIMARY"
    AUTHORISED_RECOVERY_RESEND = "AUTHORISED_RECOVERY_RESEND"


# Chunk states: the first three are send results, NOT_ATTEMPTED means the send stopped before this chunk.
CHUNK_CONFIRMED, CHUNK_FAILED, CHUNK_UNKNOWN, CHUNK_NOT_ATTEMPTED = "CONFIRMED", "FAILED", "UNKNOWN", "NOT_ATTEMPTED"
_AMBIGUOUS = (DeliveryOutcome.UNKNOWN, DeliveryOutcome.UNCONFIRMED)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ChunkResult:
    index: int                      # 0-based position in the brief; marker messages use index -1
    state: str                      # CHUNK_*
    message_id: int | None = None
    error: str | None = None     # short provider error text, never request bodies or credentials
    attempts: int = 0
    chunk_hash: str | None = None
    at: str | None = None


@dataclass
class AttemptRecord:
    brief_table: str                # 'captains_daily_briefs' | 'intelligence_briefs' | 'ref' (derived key)
    brief_id: str
    channel: str                    # 'telegram'
    content_hash: str
    kind: AttemptKind = AttemptKind.PRIMARY
    attempt_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    attempt_no: int = 1
    chunks_total: int = 0
    planned_chunks: list[int] = field(default_factory=list)   # chunk indexes this attempt set out to send (empty = all)
    chunks: list[ChunkResult] = field(default_factory=list)
    state: str = "sending"          # 'sending' (in flight / interrupted) | 'finished'
    outcome: DeliveryOutcome | None = None
    supersedes_attempt_id: str | None = None
    authorised_by: str | None = None
    reason: str | None = None
    started_at: str = field(default_factory=utcnow)
    finished_at: str | None = None

    def to_row(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["outcome"] = self.outcome.value if self.outcome else None
        d["chunks"] = [asdict(c) for c in self.chunks]
        return d

    @classmethod
    def from_row(cls, row: dict) -> AttemptRecord:
        r = dict(row)
        r["kind"] = AttemptKind(r["kind"])
        r["outcome"] = DeliveryOutcome(r["outcome"]) if r.get("outcome") else None
        r["chunks"] = [ChunkResult(**c) for c in (r.get("chunks") or [])]
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in r.items() if k in allowed})


class AttemptConflict(Exception):
    """The store refused to claim an attempt: a uniqueness rule (same attempt number, or a second marked resend) would break."""


class AttemptStore(Protocol):
    def claim(self, rec: AttemptRecord) -> None: ...
    def update(self, rec: AttemptRecord) -> None: ...
    def load(self, brief_table: str, brief_id: str, channel: str, content_hash: str | None = None) -> list[AttemptRecord]: ...
    def list_recent(self, since_iso: str) -> list[AttemptRecord]: ...


# Forward-only outcome transitions of a FINISHED attempt (mirror of intelligence_delivery_attempts_guard in the 0264 draft).
_FORWARD = {
    ("UNKNOWN", "UNCONFIRMED"), ("UNKNOWN", "PARTIAL"), ("UNKNOWN", "CONFIRMED"),
    ("UNCONFIRMED", "PARTIAL"), ("UNCONFIRMED", "CONFIRMED"),
    ("PARTIAL", "CONFIRMED"),
}
_IDENTITY = ("attempt_id", "brief_table", "brief_id", "channel", "content_hash", "kind", "attempt_no", "chunks_total",
             "planned_chunks", "supersedes_attempt_id", "authorised_by", "started_at")


def check_transition(old: dict, new: dict) -> str | None:
    """Why replacing stored row ``old`` with ``new`` is refused, or None when permitted. Pure; mirrors the SQL trigger."""
    if any(old.get(k) != new.get(k) for k in _IDENTITY):
        return "identity_columns_immutable"
    if old.get("state") == "finished":
        if new.get("state") != "finished" or new.get("finished_at") != old.get("finished_at"):
            return "finished_attempt_cannot_reopen"
        if new.get("outcome") != old.get("outcome") and (old.get("outcome"), new.get("outcome")) not in _FORWARD:
            return f"outcome_{old.get('outcome')}_to_{new.get('outcome')}_not_forward"
    oc, nc = old.get("chunks") or [], new.get("chunks") or []
    if len(nc) < len(oc):
        return "chunk_history_cannot_shrink"
    for c in oc:
        if c.get("state") == CHUNK_CONFIRMED and not any(
                n.get("index") == c.get("index") and n.get("state") == CHUNK_CONFIRMED and n.get("message_id") == c.get("message_id")
                for n in nc):
            return "confirmed_chunk_cannot_change"
    return None


def _violates_unique(existing: list[AttemptRecord], rec: AttemptRecord) -> str | None:
    """Mirror of the unique indexes in the SQL draft: (brief, channel, content, attempt_no) is unique, so two
    concurrent senders computing the same next attempt cannot both claim it; one marked resend per brief version."""
    for o in existing:
        if o.attempt_id == rec.attempt_id:
            return "attempt_id_exists"
        same = (o.brief_table, o.brief_id, o.channel, o.content_hash) == (rec.brief_table, rec.brief_id, rec.channel, rec.content_hash)
        if not same:
            continue
        if o.attempt_no == rec.attempt_no:
            return "attempt_no_taken"
        if rec.kind is AttemptKind.AUTHORISED_RECOVERY_RESEND and o.kind is AttemptKind.AUTHORISED_RECOVERY_RESEND:
            return "resend_already_made"
    return None


class InMemoryAttemptStore:
    """Thread-safe; ``snapshot``/``restore`` let tests simulate a process restart over persisted state."""

    def __init__(self, rows: list[dict] | None = None):
        self._lock = threading.Lock()
        self._rows: dict[str, dict] = {r["attempt_id"]: r for r in (rows or [])}

    def claim(self, rec: AttemptRecord) -> None:
        with self._lock:
            existing = [AttemptRecord.from_row(r) for r in self._rows.values()]
            why = _violates_unique(existing, rec)
            if why:
                raise AttemptConflict(why)
            self._rows[rec.attempt_id] = json.loads(json.dumps(rec.to_row()))
            rec._persisted = (rec.state, rec.outcome.value if rec.outcome else None)

    def update(self, rec: AttemptRecord) -> None:
        with self._lock:
            old = self._rows.get(rec.attempt_id)
            if old is None:
                raise AttemptConflict("unknown_attempt")
            new = json.loads(json.dumps(rec.to_row()))
            why = check_transition(old, new)
            if why:
                raise AttemptConflict(why)
            persisted = getattr(rec, "_persisted", None)
            if persisted is not None and persisted != (old["state"], old.get("outcome")):
                raise AttemptConflict("stale_update")      # someone else moved the row since this process read it
            self._rows[rec.attempt_id] = new
            rec._persisted = (new["state"], new.get("outcome"))

    def load(self, brief_table, brief_id, channel, content_hash=None):
        with self._lock:
            out = [AttemptRecord.from_row(r) for r in self._rows.values()
                   if (r["brief_table"], r["brief_id"], r["channel"]) == (brief_table, brief_id, channel)
                   and (content_hash is None or r["content_hash"] == content_hash)]
        for a in out:
            a._persisted = (a.state, a.outcome.value if a.outcome else None)
        return sorted(out, key=lambda a: (a.started_at, a.attempt_no))

    def snapshot(self) -> list[dict]:
        with self._lock:
            return json.loads(json.dumps(list(self._rows.values())))

    def list_recent(self, since_iso: str) -> list[AttemptRecord]:
        """Attempts started at or after ``since_iso`` (any brief), oldest first. Read only."""
        with self._lock:
            rows = [dict(r) for r in self._rows.values() if str(r.get("started_at", "")) >= since_iso]
        out = [AttemptRecord.from_row(r) for r in rows]
        for a in out:
            a._persisted = (a.state, a.outcome.value if a.outcome else None)
        return sorted(out, key=lambda a: (a.started_at, a.attempt_no))


class PostgrestAttemptStore:
    """service-role writer for ``intelligence_delivery_attempts`` (draft table, not applied under G0).
    A 409/23505 from the unique indexes becomes AttemptConflict. Constructed by callers only when the flag is on."""

    def __init__(self, url: str, key: str, timeout: int = 8):
        self.url, self.key, self.timeout = url.rstrip("/"), key, timeout

    def _headers(self, prefer: str) -> dict:
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json", "Prefer": prefer}

    def _post(self, rows: dict, prefer: str, query: str = "") -> None:
        req = urllib.request.Request(f"{self.url}/rest/v1/{TABLE}{query}", data=json.dumps(rows).encode(),
                                     headers=self._headers(prefer), method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout):  # nosec B310 - SUPABASE_URL env, https
            return

    def claim(self, rec: AttemptRecord) -> None:
        import urllib.error
        try:
            self._post(rec.to_row(), "return=minimal")
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                raise AttemptConflict("unique_violation") from exc
            raise
        rec._persisted = (rec.state, rec.outcome.value if rec.outcome else None)

    def update(self, rec: AttemptRecord) -> None:
        """Conditional PATCH, never an upsert: only the mutable columns are sent, and only when the stored row is still in the
        (state, outcome) this process last read. Zero rows matched = stale writer = AttemptConflict (nothing overwritten). The
        database trigger additionally refuses non-forward transitions and any change to a CONFIRMED chunk."""
        import urllib.error
        row = rec.to_row()
        body = {k: row[k] for k in ("chunks", "state", "outcome", "reason", "finished_at")}
        state, outcome = getattr(rec, "_persisted", ("sending", None))
        flt = {"attempt_id": f"eq.{rec.attempt_id}", "state": f"eq.{state}", "outcome": "is.null" if outcome is None else f"eq.{outcome}"}
        req = urllib.request.Request(f"{self.url}/rest/v1/{TABLE}?{urllib.parse.urlencode(flt)}", data=json.dumps(body).encode(),
                                     headers=self._headers("return=representation"), method="PATCH")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310 - SUPABASE_URL env, https
                matched = json.loads(resp.read() or b"[]")
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 409):      # trigger refusal (integrity_constraint_violation) or constraint violation
                raise AttemptConflict(f"update_refused_http_{exc.code}") from exc
            raise
        if not matched:
            raise AttemptConflict("stale_update")
        rec._persisted = (rec.state, rec.outcome.value if rec.outcome else None)

    def load(self, brief_table, brief_id, channel, content_hash=None):
        q = {"brief_table": f"eq.{brief_table}", "brief_id": f"eq.{brief_id}", "channel": f"eq.{channel}", "order": "started_at.asc"}
        if content_hash:
            q["content_hash"] = f"eq.{content_hash}"
        req = urllib.request.Request(f"{self.url}/rest/v1/{TABLE}?{urllib.parse.urlencode(q)}",
                                     headers=self._headers("return=representation"))
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310 - SUPABASE_URL env, https
            out = [AttemptRecord.from_row(r) for r in json.loads(resp.read())]
        for a in out:
            a._persisted = (a.state, a.outcome.value if a.outcome else None)
        return out

    LIST_LIMIT = 500

    def list_recent(self, since_iso: str) -> list[AttemptRecord]:
        """Attempts started at or after ``since_iso`` (any brief), oldest first (SELECT only, bounded by LIST_LIMIT).
        Fetched newest-first so an overflow of LIST_LIMIT drops the OLDEST rows, never the newest interrupted attempts."""
        q = {"started_at": f"gte.{since_iso}", "order": "started_at.desc", "limit": str(self.LIST_LIMIT)}
        req = urllib.request.Request(f"{self.url}/rest/v1/{TABLE}?{urllib.parse.urlencode(q)}", headers=self._headers("return=representation"))
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310 - SUPABASE_URL env, https; SELECT only
            out = [AttemptRecord.from_row(r) for r in json.loads(resp.read())]
        for a in out:
            a._persisted = (a.state, a.outcome.value if a.outcome else None)
        return sorted(out, key=lambda a: (a.started_at, a.attempt_no))


# ----------------------------------------------------------------------------- outcome logic

def outcome_from_chunks(chunks: list[ChunkResult], total: int) -> DeliveryOutcome:
    """Outcome of ONE attempt from its chunk results (ambiguity is never promoted to success)."""
    confirmed = sum(1 for c in chunks if c.state == CHUNK_CONFIRMED and c.index >= 0)
    if total > 0 and confirmed == total:
        return DeliveryOutcome.CONFIRMED
    if confirmed > 0:
        return DeliveryOutcome.PARTIAL
    if any(c.state == CHUNK_UNKNOWN for c in chunks):
        return DeliveryOutcome.UNKNOWN
    return DeliveryOutcome.FAILED


def attempt_outcome(rec: AttemptRecord) -> DeliveryOutcome:
    total = len(rec.planned_chunks) if rec.planned_chunks else rec.chunks_total
    return outcome_from_chunks(rec.chunks, total)


@dataclass
class Rollup:
    outcome: DeliveryOutcome
    chunks_total: int
    confirmed_chunks: list[int]
    ambiguous_chunks: list[int]
    recovery_resends: int
    possible_duplicate_chunks: list[int]    # chunks a resend covered while an earlier attempt may also have delivered them
    disclosure: str | None


def rollup(attempts: list[AttemptRecord]) -> Rollup | None:
    """Row-level delivery status across all attempts of one (brief, channel, content)."""
    if not attempts:
        return None
    total = max(a.chunks_total for a in attempts)
    confirmed: set[int] = set()
    ambiguous: set[int] = set()
    for a in attempts:
        for c in a.chunks:
            if c.index < 0:
                continue
            if c.state == CHUNK_CONFIRMED:
                confirmed.add(c.index)
            elif c.state == CHUNK_UNKNOWN:
                ambiguous.add(c.index)
    ambiguous -= confirmed
    resends = [a for a in attempts if a.kind is AttemptKind.AUTHORISED_RECOVERY_RESEND]
    possible_dups: set[int] = set()
    for rs in resends:
        for c in rs.chunks:
            if c.state == CHUNK_CONFIRMED and c.index >= 0:
                earlier_ambiguous = any(o.attempt_id != rs.attempt_id and o.started_at <= rs.started_at
                                        and any(x.index == c.index and x.state == CHUNK_UNKNOWN for x in o.chunks)
                                        for o in attempts)
                if earlier_ambiguous:
                    possible_dups.add(c.index)
    if total and len(confirmed) == total:
        outcome = DeliveryOutcome.CONFIRMED
    elif confirmed:
        outcome = DeliveryOutcome.PARTIAL
    elif any(a.outcome is DeliveryOutcome.UNCONFIRMED for a in attempts):
        outcome = DeliveryOutcome.UNCONFIRMED
    elif ambiguous or any(a.outcome is DeliveryOutcome.UNKNOWN or a.state != "finished" for a in attempts):
        outcome = DeliveryOutcome.UNKNOWN
    else:
        outcome = DeliveryOutcome.FAILED
    disclosure = None
    if resends:
        disclosure = (f"{len(resends)} authorised recovery resend(s) recorded; "
                      + (f"chunk(s) {sorted(possible_dups)} may have been delivered twice." if possible_dups
                         else "no chunk is known to have been delivered twice."))
    if outcome is DeliveryOutcome.PARTIAL and total:
        missing = [i + 1 for i in range(total) if i not in confirmed]
        gap_txt = f"PARTIAL: part(s) {missing} of {total} not delivered" + ("" if not ambiguous else f" (part(s) {sorted(i + 1 for i in ambiguous)} unconfirmed)")
        disclosure = f"{gap_txt}. {disclosure}" if disclosure else gap_txt
    return Rollup(outcome, total, sorted(confirmed), sorted(ambiguous), len(resends), sorted(possible_dups), disclosure)


# ----------------------------------------------------------------------------- policy

@dataclass
class Authorisation:
    allowed: bool
    reason: str
    preventable_duplicate: bool = False     # True when the refused action WOULD have been one
    supersedes_attempt_id: str | None = None
    chunk_indexes: list[int] | None = None
    attempt_no: int = 1


def authorise_attempt(prior: list[AttemptRecord], kind: AttemptKind, *, authorised_by: str | None = None,
                      chunks_total: int = 0) -> Authorisation:
    """Decide whether a new attempt may be sent. This is where 'preventable duplicate = 0' is enforced."""
    n = len(prior) + 1
    in_flight = [a for a in prior if a.state != "finished"]
    if kind is AttemptKind.PRIMARY:
        if in_flight:
            return Authorisation(False, "attempt_in_flight_or_interrupted", True, attempt_no=n)
        if not prior:
            return Authorisation(True, "first_primary", attempt_no=n)
        roll = rollup(prior)
        if roll.outcome is DeliveryOutcome.FAILED:
            return Authorisation(True, "retry_after_definite_failure", attempt_no=n)
        if roll.outcome is DeliveryOutcome.PARTIAL and not roll.ambiguous_chunks:
            missing = [i for i in range(chunks_total or roll.chunks_total) if i not in roll.confirmed_chunks]
            return Authorisation(True, "continue_partial_definite_failure", chunk_indexes=missing, attempt_no=n)
        return Authorisation(False, f"primary_already_{roll.outcome.value.lower()}", True, attempt_no=n)

    # recovery resend
    if not authorised_by:
        return Authorisation(False, "resend_not_authorised", True, attempt_no=n)
    if authorised_by not in AUTHORISERS:
        return Authorisation(False, "authoriser_not_enumerated", True, attempt_no=n)
    if in_flight:
        return Authorisation(False, "attempt_in_flight_or_interrupted", True, attempt_no=n)
    roll = rollup(prior)
    if roll is None:
        return Authorisation(False, "resend_without_prior_attempt", True, attempt_no=n)
    if roll.outcome is DeliveryOutcome.CONFIRMED:
        return Authorisation(False, "resend_of_confirmed", True, attempt_no=n)
    if roll.outcome is DeliveryOutcome.FAILED or not roll.ambiguous_chunks and roll.outcome is not DeliveryOutcome.UNCONFIRMED \
            and not any(a.outcome in _AMBIGUOUS for a in prior):
        return Authorisation(False, "no_ambiguity_continue_as_primary", True, attempt_no=n)
    ambiguous_attempts = [a for a in prior if a.outcome in _AMBIGUOUS or any(c.state == CHUNK_UNKNOWN for c in a.chunks)]
    if not ambiguous_attempts:
        return Authorisation(False, "no_ambiguity_continue_as_primary", True, attempt_no=n)
    target = ambiguous_attempts[-1]
    if any(a.kind is AttemptKind.AUTHORISED_RECOVERY_RESEND for a in prior):      # policy: ONE marked resend per brief version
        return Authorisation(False, "resend_already_made", True, attempt_no=n)
    missing = [i for i in range(chunks_total or roll.chunks_total) if i not in roll.confirmed_chunks]
    return Authorisation(True, "ambiguous_prior_attempt", supersedes_attempt_id=target.attempt_id, chunk_indexes=missing, attempt_no=n)


def plan_recovery(attempts: list[AttemptRecord], *, authorised_by: str | None = POLICY_AUTHORISER) -> Authorisation:
    """What may be done for a brief whose delivery is not CONFIRMED. Never sends."""
    roll = rollup(attempts)
    if roll is None:
        return Authorisation(False, "no_attempts")
    if roll.outcome is DeliveryOutcome.CONFIRMED:
        return Authorisation(False, "resend_of_confirmed", True)
    if roll.outcome is DeliveryOutcome.FAILED or (roll.outcome is DeliveryOutcome.PARTIAL and not roll.ambiguous_chunks):
        return authorise_attempt(attempts, AttemptKind.PRIMARY, chunks_total=roll.chunks_total)   # plain continue, no marker
    return authorise_attempt(attempts, AttemptKind.AUTHORISED_RECOVERY_RESEND, authorised_by=authorised_by, chunks_total=roll.chunks_total)


def duplicate_report(attempts: list[AttemptRecord]) -> dict:
    """Measured separately: preventable duplicates (target 0) vs authorised recovery resends (disclosed)."""
    preventable: list[str] = []
    seen: dict[int, int] = {}
    for a in attempts:
        if a.kind is AttemptKind.PRIMARY:
            for c in a.chunks:
                if c.state == CHUNK_CONFIRMED and c.index >= 0:
                    seen[c.index] = seen.get(c.index, 0) + 1
    if any(v > 1 for v in seen.values()):
        preventable.append("primary_sent_more_than_once")
    ordered = sorted(attempts, key=lambda a: a.started_at)
    for i, a in enumerate(ordered):
        if a.kind is not AttemptKind.AUTHORISED_RECOVERY_RESEND:
            continue
        before = ordered[:i]
        if not any(o.outcome in _AMBIGUOUS or (o.outcome is DeliveryOutcome.PARTIAL and any(c.state == CHUNK_UNKNOWN for c in o.chunks)) for o in before):
            preventable.append("resend_without_prior_ambiguity")
        confirmed_before = {c.index for o in before for c in o.chunks if c.state == CHUNK_CONFIRMED and c.index >= 0}
        if any(c.index in confirmed_before for c in a.chunks if c.index >= 0 and c.state != CHUNK_NOT_ATTEMPTED):
            preventable.append("resend_of_confirmed_chunk")
        if sum(1 for o in ordered if o.kind is AttemptKind.AUTHORISED_RECOVERY_RESEND) > 1:
            preventable.append("more_than_one_resend")
    roll = rollup(attempts)
    return {
        "preventable_duplicates": len(preventable), "preventable_detail": preventable,
        "authorised_recovery_resends": sum(1 for a in attempts if a.kind is AttemptKind.AUTHORISED_RECOVERY_RESEND),
        "possible_duplicate_chunks": roll.possible_duplicate_chunks if roll else [],
        "exactly_once_claimed": False,
    }


# ----------------------------------------------------------------------------- execution

SendChunk = Callable[[str], ChunkResult]     # sends ONE piece; must classify, never raise for provider errors
Splitter = Callable[[str], list[str]]


@dataclass
class DeliveryResult:
    sent: bool                  # True when at least one send was attempted
    refused_reason: str | None
    attempt: AttemptRecord | None
    outcome: DeliveryOutcome | None
    rollup: Rollup | None
    preventable_duplicate_prevented: bool = False


def _finish(rec: AttemptRecord, store: AttemptStore) -> bool:
    """Persist the terminal state. False (nothing overwritten) when the store refuses: the stored row moved on without us."""
    rec.outcome = attempt_outcome(rec)
    rec.state = "finished"
    rec.finished_at = utcnow()
    try:
        store.update(rec)
    except AttemptConflict as exc:
        log.warning("[delivery-record] finish refused for attempt %s (%s): stored record kept", rec.attempt_id, exc)
        return False
    return True


def _persist(rec: AttemptRecord, store: AttemptStore) -> bool:
    try:
        store.update(rec)
        return True
    except AttemptConflict as exc:
        log.warning("[delivery-record] update refused for attempt %s (%s): stopping this attempt", rec.attempt_id, exc)
        return False


def deliver(brief_table: str, brief_id: str, text: str, *, channel: str, store: AttemptStore, split: Splitter,
            send_chunk: SendChunk, kind: AttemptKind = AttemptKind.PRIMARY, authorised_by: str | None = None) -> DeliveryResult:
    """Send ``text`` once under the policy, recording the attempt durably. The first chunk that fails or is
    ambiguous stops the attempt (no out-of-order or blind continuation); remaining chunks are NOT_ATTEMPTED.
    If the store refuses an update (a stale writer; the stored attempt moved on) nothing further is sent and the stored
    record is left as it is; the result's refused_reason says so and the local outcome is what this process observed."""
    h = content_hash(text)
    pieces = split(text)
    prior = store.load(brief_table, brief_id, channel, h)
    auth = authorise_attempt(prior, kind, authorised_by=authorised_by, chunks_total=len(pieces))
    if not auth.allowed:
        return DeliveryResult(False, auth.reason, None, None, rollup(prior), preventable_duplicate_prevented=auth.preventable_duplicate)
    if auth.chunk_indexes is not None:
        stored_total = max((a.chunks_total for a in prior), default=0)
        if stored_total != len(pieces):
            return DeliveryResult(False, "chunking_changed_since_primary", None, None, rollup(prior))
    todo = auth.chunk_indexes if auth.chunk_indexes is not None else list(range(len(pieces)))
    rec = AttemptRecord(brief_table, brief_id, channel, h, kind=kind, attempt_no=auth.attempt_no, chunks_total=len(pieces),
                        planned_chunks=list(todo) if auth.chunk_indexes is not None else [],
                        supersedes_attempt_id=auth.supersedes_attempt_id, authorised_by=authorised_by, reason=auth.reason)
    try:
        store.claim(rec)                        # atomic guard: a concurrent sender loses here and sends nothing
    except AttemptConflict as exc:
        return DeliveryResult(False, f"claim_refused:{exc}", None, None, rollup(store.load(brief_table, brief_id, channel, h)),
                              preventable_duplicate_prevented=True)
    stopped = False
    lost = False
    marker_pending = False
    if kind is AttemptKind.AUTHORISED_RECOVERY_RESEND:
        # The marker is merged into the FIRST resent content chunk (never sent alone first), so the Captain never sees "resent" without content.
        # It is recorded as chunk -1 (CONFIRMED, merged, no send of its own).
        rec.chunks.append(ChunkResult(-1, CHUNK_CONFIRMED, error="marker_merged_into_first_resent_chunk", attempts=0, at=utcnow()))
        lost = not _persist(rec, store)
        stopped = lost
        marker_pending = True
    gap: list[int] = []          # chunks that definitely did NOT deliver; later chunks still go (no duplicate risk) and say so
    for idx in todo:
        if stopped:
            rec.chunks.append(ChunkResult(idx, CHUNK_NOT_ATTEMPTED, chunk_hash=content_hash(pieces[idx])))
            continue
        prefix = ""
        if marker_pending:
            prefix += f"{RECOVERY_MARKER}\n\n"
        if gap:
            prefix += _gap_notice(gap, len(pieces))
        body = pieces[idx]
        if prefix and len(prefix) + len(body) > TELEGRAM_LIMIT:
            if marker_pending:                                   # oversize: the marker goes immediately BEFORE the content send, on its own
                mres = _send_one(send_chunk, RECOVERY_MARKER, -1)
                if mres.state != CHUNK_CONFIRMED:
                    rec.chunks.append(mres)
                    lost = not _persist(rec, store)
                    stopped = True
                    rec.chunks.append(ChunkResult(idx, CHUNK_NOT_ATTEMPTED, chunk_hash=content_hash(body)))
                    continue
            prefix = ""
        carried_marker, marker_pending = marker_pending, False
        res = _send_one(send_chunk, prefix + body, idx)
        res.chunk_hash = content_hash(body)                      # the record is about the content chunk, not the prefixed text
        rec.chunks.append(res)
        lost = not _persist(rec, store)         # persisted after every chunk: a restart sees exactly what happened
        if res.state == CHUNK_FAILED and not lost:
            gap.append(idx)                      # a definite non-delivery: continue, as the legacy path does (no duplicate risk)
            marker_pending = carried_marker      # the marker did not reach the Captain: it rides on the next chunk
        elif res.state == CHUNK_CONFIRMED and prefix:
            gap = []                             # the notice reached the Captain with this chunk
        stopped = lost or res.state not in (CHUNK_CONFIRMED, CHUNK_FAILED)     # an AMBIGUOUS chunk still stops the attempt
    if lost:
        rec.outcome = attempt_outcome(rec)
        return DeliveryResult(True, "update_refused_stale_attempt", rec, rec.outcome, rollup(store.load(brief_table, brief_id, channel, h)))
    if not _finish(rec, store):
        return DeliveryResult(True, "update_refused_stale_attempt", rec, rec.outcome, rollup(store.load(brief_table, brief_id, channel, h)))
    return DeliveryResult(True, None, rec, rec.outcome, rollup(store.load(brief_table, brief_id, channel, h)))


def _gap_notice(missing: list[int], total: int) -> str:
    parts = ", ".join(str(i + 1) for i in missing)
    return f"[Part {parts} of {total} of this brief could not be delivered.]\n\n"


def _send_one(send_chunk: SendChunk, piece: str, index: int) -> ChunkResult:
    try:
        res = send_chunk(piece)
    except Exception as exc:  # noqa: BLE001 - a raising sender after the request may have been written is ambiguous, never success
        res = ChunkResult(index, CHUNK_UNKNOWN, error=f"{type(exc).__name__}", attempts=1)
    res.index = index
    res.chunk_hash = res.chunk_hash or content_hash(piece)
    res.at = res.at or utcnow()
    return res


def recover_interrupted(brief_table: str, brief_id: str, channel: str, store: AttemptStore) -> list[AttemptRecord]:
    """Restart recovery: an attempt still 'sending' was interrupted. Its in-flight chunk is ambiguous (UNKNOWN),
    later chunks were never attempted. Marks it finished; the outcome is derived, never assumed."""
    fixed = []
    for a in store.load(brief_table, brief_id, channel):
        if a.state == "finished":
            continue
        sent = {c.index for c in a.chunks}
        plan = a.planned_chunks or list(range(max(a.chunks_total, 0)))
        pending = [i for i in plan if i not in sent]
        if pending:
            a.chunks.append(ChunkResult(pending[0], CHUNK_UNKNOWN, error="interrupted_in_flight", at=utcnow()))
            for i in pending[1:]:
                a.chunks.append(ChunkResult(i, CHUNK_NOT_ATTEMPTED))
        elif not a.chunks:
            a.chunks.append(ChunkResult(0, CHUNK_UNKNOWN, error="interrupted_in_flight", at=utcnow()))
        a.reason = (a.reason or "") + ";recovered_after_restart"
        if _finish(a, store):
            fixed.append(a)
    return fixed


def reconcile(attempts: list[AttemptRecord], store: AttemptStore, *,
              lookup: Callable[[AttemptRecord, ChunkResult], int | None] | None = None) -> list[AttemptRecord]:
    """Reconciliation pass over ambiguous attempts. ``lookup`` returns a provider message id when the provider can
    prove delivery. Telegram offers no such lookup (lookup=None), so ambiguity becomes UNCONFIRMED, never CONFIRMED."""
    changed = []
    for a in attempts:
        if a.state != "finished":
            continue
        touched = False
        for c in a.chunks:
            if c.state == CHUNK_UNKNOWN and lookup is not None:
                mid = lookup(a, c)
                if mid is not None:
                    c.state, c.message_id, c.error, touched = CHUNK_CONFIRMED, mid, "reconciled_by_provider_lookup", True
        new = attempt_outcome(a) if touched else a.outcome
        if new is DeliveryOutcome.UNKNOWN:
            new = DeliveryOutcome.UNCONFIRMED
            a.reason = (a.reason or "") + ";provider_cannot_confirm"
            touched = True
        if touched:
            a.outcome = new
            try:
                store.update(a)
            except AttemptConflict as exc:      # the stored attempt moved on (or the transition is not forward): keep the stored record
                log.warning("[delivery-record] reconcile refused for attempt %s (%s)", a.attempt_id, exc)
                continue
            changed.append(a)
    return changed
