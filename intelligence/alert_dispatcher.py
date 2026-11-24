"""Immediate-alert dispatcher for IMMEDIATE_ALERT incidents (default OFF, dry-run by default, never sends in tests).

For each clustered incident (``incident_clustering``) with its delivery tier (``delivery_tiers``) it decides, once per incident:

  kind "alert"        the first time an incident reaches IMMEDIATE_ALERT
  kind "restoration"  once, when an already-alerted incident is restored (full restoration claim)
  (nothing)           every other pass: an incident is never alerted twice, a restoration is never repeated, a later tier change
                      or a growing report count sends nothing

Incident identity is ``tiered_brief.incident_id`` (the one canonical id shared with the brief, Home, Decisions and the portal; carried as ``incident_id`` and ``incident_key``). It survives growth: an incident is the same incident as a stored one when they share ANY report id.

Freshness guard (independent of the tier rules): an alert needs a factual report published within INCIDENT_ALERT_FRESH_HOURS (default 6) with a
verified publication time, from a non-register source. Back-fills, retrospective releases and statutory outage registers never alert.

Safety model (all read at call time):
  INCIDENT_ALERTS_V1            master flag, default OFF: ``process`` returns [] and touches nothing
  INCIDENT_ALERTS_SEND          must be truthy for a real send ...
  INCIDENT_ALERT_DESTINATION    ... AND a destination (e.g. a Telegram chat id) must be configured ...
  a ``sender`` callable          ... AND one must be passed in. Missing any of the three means dry-run: the payload is logged and
                                 returned with ``sent=False``. Nothing in this module imports a transport.
Dry-run state is kept apart from real-send state (``dry_*`` fields), so rehearsing never consumes the "once" of a later real send.
Rate limit: at most ``max_per_window`` sends (real or dry, counted separately) per ``window``; the rest are deferred (state untouched,
retried on the next pass) and returned with ``deferred=True``.

State lives behind ``AlertStore``: ``InMemoryAlertStore`` (tests, replay) or the durable ``intelligence.alert_store.PostgrestAlertStore`` (claim-before-send). Tables: PROD (state+sends), claims drafted NOT applied in
``docs/migration-drafts/DRAFT-incident-alert-claims.sql``. Scheduled caller: ``intelligence.alert_runner``; sender: ``intelligence.alert_telegram``.
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

from intelligence import delivery_tiers as dt
from intelligence import freshness as fr
from intelligence import incident_clustering as ic
from intelligence import tiered_brief as tb

log = logging.getLogger(__name__)

FLAG = "INCIDENT_ALERTS_V1"
SEND_FLAG = "INCIDENT_ALERTS_SEND"
DESTINATION_ENV = "INCIDENT_ALERT_DESTINATION"
_TRUE = ("1", "true", "yes", "on")
FRESH_ENV = fr.ALERT_FRESH_ENV                  # one shared freshness definition (intelligence/freshness.py): tiers, dispatcher and brief agree
DEFAULT_FRESH_HOURS = fr.ALERT_FRESH_HOURS
# Statutory/regulator outage registers and similar retrospective listings are records of past outages, never live reports.
_REGISTER_SOURCE_RX = re.compile(r"\b(?:outage register|national outage register|register)\b|\bstatutory\b", re.IGNORECASE)
DEFAULT_MAX_PER_WINDOW = 3
DEFAULT_WINDOW = timedelta(hours=1)


def enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in _TRUE


def real_send_allowed() -> bool:
    """True only with the explicit send flag AND a configured destination."""
    return os.getenv(SEND_FLAG, "").strip().lower() in _TRUE and bool(os.getenv(DESTINATION_ENV, "").strip())


def fresh_window() -> timedelta:
    return fr.alert_window()


def is_register_source(source: str | None) -> bool:
    return bool(_REGISTER_SOURCE_RX.search(source or ""))


def alertable_reports(inc: ic.Incident, now: datetime) -> list[ic.ClassifiedReport]:
    """Factual reports this dispatcher will alert on, enforced here independently of the tier rules: published within the freshness window
    (default 6 h) with a VERIFIED publication time (a collection-time fallback proves nothing), and not from a register-type source. A
    back-filled or retrospective report (an ASIC release dated two weeks ago, an outage-register entry) can never be the reason to alert."""
    window = fresh_window()
    return [r for r in inc.reports if r.relation in (ic.NEW, ic.SUBSEQUENT) and r.candidate.time_verified and r.candidate.published
            and fr.within(r.candidate.published, now, window) and not is_register_source(r.candidate.source)]


@dataclass
class AlertState:
    incident_key: str
    event_ids: set = field(default_factory=set)
    headline: str = ""
    alerted_at: datetime | None = None            # real send
    restoration_sent_at: datetime | None = None   # real send
    dry_alerted_at: datetime | None = None
    dry_restoration_at: datetime | None = None


class AlertStore(Protocol):
    def find(self, event_ids: set) -> AlertState | None: ...
    def put(self, state: AlertState) -> None: ...
    def log_send(self, at: datetime, mode: str, incident_key: str = "", kind: str = "alert") -> None: ...
    def sends_since(self, since: datetime, mode: str) -> int: ...
    # Optional (a store without them just never blocks a send): atomic claim-before-send. ``claim`` returns a token or None (already sent or
    # claimed by someone else), ``complete`` records the send, ``release`` gives the claim back after a failed send.
    def claim(self, kind: str, incident_key: str) -> str | None: ...
    def complete(self, kind: str, incident_key: str, token: str, now: datetime) -> bool: ...
    def release(self, kind: str, incident_key: str, token: str) -> bool: ...


class InMemoryAlertStore:
    def __init__(self):
        self.states: dict[str, AlertState] = {}
        self.sends: list[tuple[datetime, str]] = []
        self._claims: dict[tuple[str, str], str] = {}

    def find(self, event_ids: set) -> AlertState | None:
        for st in self.states.values():
            if st.event_ids & event_ids:
                return st
        return None

    def put(self, state: AlertState) -> None:
        self.states[state.incident_key] = state

    def log_send(self, at: datetime, mode: str, incident_key: str = "", kind: str = "alert") -> None:
        self.sends.append((at, mode))

    def sends_since(self, since: datetime, mode: str) -> int:
        return sum(1 for t, m in self.sends if t > since and m == mode)

    def claim(self, kind: str, incident_key: str) -> str | None:
        st = self.states.get(incident_key)
        if st is None or (kind, incident_key) in self._claims:
            return None
        if (st.alerted_at if kind == "alert" else st.restoration_sent_at) is not None:
            return None
        token = self._claims[(kind, incident_key)] = uuid.uuid4().hex
        return token

    def complete(self, kind: str, incident_key: str, token: str, now: datetime) -> bool:
        if self._claims.get((kind, incident_key)) != token:
            return False
        del self._claims[(kind, incident_key)]
        setattr(self.states[incident_key], "alerted_at" if kind == "alert" else "restoration_sent_at", now)
        return True

    def release(self, kind: str, incident_key: str, token: str) -> bool:
        return self._claims.pop((kind, incident_key), None) == token


def build_payload(kind: str, inc: ic.Incident, td: dt.TierDecision, now: datetime, pinned_id: str | None = None,
                  pinned_headline: str | None = None) -> dict:
    """The message an operator would receive. Facts only: what the cited reports state, nothing inferred."""
    key = pinned_id or tb.incident_id(inc)
    link = tb.incident_link(key)
    d = inc.decision
    status = tb.RESTORATION_LABEL.get(inc.restoration_status, inc.restoration_status)
    head = "RESTORED" if kind == "restoration" else "ALERT"
    # The incident headline is re-chosen on every pass and can become a hedged or forecast report ("crews race to restore ..."). A message
    # that says RESTORED must not carry that as its title: pin the headline the original alert used.
    title = pinned_headline or d.headline.title
    n_fact = td.evidence.get("n_factual")
    counts = f"{inc.n_reports} grouped, {n_fact} factual" if isinstance(n_fact, int) and n_fact < inc.n_reports else f"{inc.n_reports}"
    lines = [f"{head}: {title}",
             f"Status: {status}. Reports: {counts} ({td.evidence.get('independent_publishers', '?')} independent publishers). Evidence: {d.evidence_status}.",
             f"Why this interrupts: {td.reasons[0]}"]
    if kind == "restoration":
        rest = [r for r in inc.reports if r.relation == ic.RESTORATION_UPDATE]
        if rest:
            lines.append(f"Restoration report: {rest[-1].candidate.title} [{str(rest[-1].event_id)[:8]}]")
    else:
        new = [r for r in inc.reports if r.relation == ic.NEW]
        if new:
            lines.append(f"First report: {new[0].candidate.title} [{str(new[0].event_id)[:8]}]")
    lines.append(f"Incident: {key}")
    lines.append(f"View: {link}")
    return {"kind": kind, "incident_id": key, "incident_key": key, "link": link, "headline": title, "tier": td.tier, "restoration_status": inc.restoration_status,
            "n_reports": inc.n_reports, "event_ids": sorted(r.event_id for r in inc.reports), "generated_at": now.isoformat(), "text": "\n".join(lines)}


def _decide(inc: ic.Incident, td: dt.TierDecision, st: AlertState | None, real: bool, now: datetime) -> str | None:
    alerted = (st.alerted_at if real else st.dry_alerted_at) if st else None
    rest = (st.restoration_sent_at if real else st.dry_restoration_at) if st else None
    if alerted is None:
        # A first alert needs the tier. A restored incident that was never alerted (e.g. restored before it was fresh) is not alerted retroactively.
        if td.tier == dt.IMMEDIATE_ALERT and inc.restoration_status not in ("restored", "unknown") and alertable_reports(inc, now):
            return "alert"
        return None
    if rest is None and inc.restoration_status == "restored" and any(r.relation == ic.RESTORATION_UPDATE and r.restoration == "full" for r in inc.reports):
        return "restoration"
    return None


def process(incidents: list[ic.Incident], *, now: datetime | None = None, store: AlertStore | None = None,
            sender: Callable[[dict, str], bool] | None = None, max_per_window: int = DEFAULT_MAX_PER_WINDOW,
            window: timedelta = DEFAULT_WINDOW, force: bool | None = None, dry_only: bool = False, deadline: float | None = None) -> list[dict]:
    """One dispatcher pass. Returns the payloads handled (each with ``sent``, ``dry_run`` and ``deferred``). ``force`` overrides the master
    flag for tests/replay; it never enables a real send. ``dry_only`` makes a real send impossible (replay tools). ``deadline`` is a
    ``time.monotonic()`` value after which no further incident is handled (bounded runtime; the rest is picked up on the next pass).

    A real send is claim-before-send when the store supports it: only the caller that wins ``store.claim`` sends; ``complete`` records the
    send afterwards and ``release`` hands the claim back after a failed send, so a failure stays retryable and nothing is sent twice."""
    if not (enabled() if force is None else force):
        return []
    now = now or datetime.now(timezone.utc)
    store = store if store is not None else InMemoryAlertStore()
    real = real_send_allowed() and sender is not None and not dry_only
    mode = "real" if real else "dry"
    out: list[dict] = []
    ordered = sorted(incidents, key=lambda i: (i.first_report_time or now, tb.incident_id(i)))
    for inc in ordered:
        if deadline is not None and time.monotonic() > deadline:
            log.warning("[incident-alert] time budget reached; remaining incidents wait for the next pass")
            break
        td = dt.tier_for_incident(inc, now=now)
        ids = {r.event_id for r in inc.reports}
        st = store.find(ids)
        kind = _decide(inc, td, st, real, now)
        if st is not None:
            st.event_ids |= ids                     # a growing incident keeps its identity
        if kind is None:
            if st is not None:
                store.put(st)
            continue
        payload = build_payload(kind, inc, td, now, st.incident_key if st else None, st.headline if (st and kind == "restoration" and st.headline) else None)
        payload.update(dry_run=not real, sent=False, deferred=False, destination=("configured" if real else None))
        if store.sends_since(now - window, mode) >= max_per_window:
            payload["deferred"] = True
            log.info("[incident-alert] rate limited, deferring %s %s", kind, payload["incident_key"])
            out.append(payload)
            if st is not None:
                store.put(st)
            continue
        token = None
        if real:
            claim = getattr(store, "claim", None)
            if claim is not None:
                if st is None:                        # the state row must exist before it can be claimed
                    st = AlertState(payload["incident_key"], set(ids), payload["headline"])
                    store.put(st)
                token = claim(kind, st.incident_key)
                if token is None:
                    payload["claimed_elsewhere"] = True
                    log.info("[incident-alert] %s %s already sent or claimed; not sending", kind, payload["incident_key"])
                    out.append(payload)
                    continue
            try:
                payload["sent"] = bool(sender(payload, os.getenv(DESTINATION_ENV, "").strip()))
            except Exception as exc:  # noqa: BLE001 - a failed send must not mark the alert as sent
                log.warning("[incident-alert] send failed for %s: %s", payload["incident_key"], exc)
                payload["error"] = str(exc)
        else:
            log.info("[incident-alert][dry-run] %s %s: %s", kind, payload["incident_key"], payload["headline"])
        if real and not payload["sent"]:
            if token is not None:
                try:
                    store.release(kind, st.incident_key, token)          # failed send: give the claim back so the next pass retries
                except Exception as exc:  # noqa: BLE001 - claim stays held (at-most-once) and is reported
                    log.error("[incident-alert] could not release claim for %s: %s", payload["incident_key"], exc)
            out.append(payload)                      # not recorded: it will be retried on the next pass
            if st is not None:
                store.put(st)
            continue
        st = st or AlertState(payload["incident_key"], set(ids), payload["headline"])
        if real and token is not None:
            try:
                store.complete(kind, st.incident_key, token, now)
            except Exception as exc:  # noqa: BLE001 - already delivered; the claim stays held so it can never be sent again
                log.error("[incident-alert] SENT %s %s but could not record it (claim stays held, will not resend): %s", kind, payload["incident_key"], exc)
        stamp = "alerted_at" if (kind == "alert" and real) else "restoration_sent_at" if real else "dry_alerted_at" if kind == "alert" else "dry_restoration_at"
        setattr(st, stamp, now)
        try:
            store.put(st)
            store.log_send(now, mode, st.incident_key, kind)
        except Exception as exc:
            if not real:
                raise
            log.error("[incident-alert] ledger write failed after send for %s: %s", payload["incident_key"], exc)
        out.append(payload)
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m intelligence.alert_dispatcher", description="Incident alert tools (flags stay OFF; neither mode needs them).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--controlled-test", action="store_true", help="send ONE '[TEST] Alert path check' alert through the real sender; needs --yes")
    g.add_argument("--replay-7d-dry-run", action="store_true", help="print what would have alerted over the last 7 days (read-only, never sends)")
    ap.add_argument("--yes", action="store_true", help="confirm a real controlled-test send")
    ap.add_argument("--destination", default=None, help=f"'xo' (XO default chat) or a chat id; default ${DESTINATION_ENV}")
    ap.add_argument("--window-hours", type=float, default=6.0, help="controlled-test suppression window")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from intelligence import alert_runner
    if args.controlled_test:
        return alert_runner.controlled_test(yes=args.yes, destination=args.destination, window_hours=args.window_hours)
    alert_runner.replay(alert_runner.load_events(168, limit=5000))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
