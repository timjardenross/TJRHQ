"""Attention Engine Drill — deliberately-invoked end-to-end pipeline test.

Context (diagnosed, not guessed, 2026-08-22): `interrupt_now`
(core/platform/attention_engine.py's `AttentionThresholds.interrupt_importance_floor`
= 75 AND `interrupt_confidence_floor` = 70, both required simultaneously) is a
correct, deliberately conservative design — it has simply never fired on real
data, because the real event stream `intelligence/scheduler.py`'s
`continuous_attention_evaluation` job polls every 10 minutes is dominated by
repeating signal types (e.g. `health.readiness.scored`) that never cross both
floors together. That is an input-side gap, not an engine bug, and this
module does not change the thresholds or feed real events into them.

What this module actually is: a synthetic, unmistakably-labelled drill that
proves the *pipe* still works — `evaluate_batch()` classification ->
`assemble_captain_brief()` -> `core.platform.interrupt_dispatcher
.dispatch_interrupt_now()` -> `notification_service.notify()` -> a real
Telegram send to the Captain's configured chat — end to end, on demand,
without waiting for a real event that may never arrive. If this pipe silently
broke somewhere between here and Telegram, nothing would ever notice, because
nothing has exercised it since USS-TJR-MSN-0339 WP2 built it.

Every synthetic event this module builds carries `[DRILL]` in its
`recommended_action` text (which becomes the Telegram message body via
`interrupt_dispatcher.dispatch_interrupt_now()`) so it can never be mistaken
for a real interrupt if it reaches the Captain's phone — which, run
undried-run, it is meant to.

Deliberately NOT wired into `continuous_attention_evaluation` (the real
10-minute poll loop) — that would pollute the real `core_events` stream with
synthetic data. This is a separate, deliberately-invoked path. It also does
not call `core.platform.event_bus.publish_event()` — the drill event is
constructed in-memory only and never written to `core_events`. Its
`mark_event_status()` call inside `dispatch_interrupt_now()` (fired only
after a successful notify()) targets a `drill-*` event_id, which isn't a
valid `core_events.event_id` UUID — confirmed live 2026-08-22: this makes
the UPDATE 400 on a Postgres type-cast error rather than matching zero rows,
but `mark_event_status()` catches that itself and logs a non-blocking
warning (event_bus.py's own contract: "never raises"), so it does not affect
this drill's own pass/fail result.

Usage:
  python -m core.platform.attention_drill              Full drill: classify + real Telegram dispatch
  python -m core.platform.attention_drill --dry-run     Classify only; skip the real dispatch/Telegram send
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("attention-drill")

_REPO_ROOT = Path(__file__).resolve().parents[2]

DRILL_MARKER = "[DRILL] Attention Engine test-fire — not a real alert."


def _load_dotenv() -> None:
    """This module must be runnable directly via `python -m
    core.platform.attention_drill` without relying on the invoking shell
    having already sourced .env, and without relying on systemd's
    EnvironmentFile= (which is how this same code path gets its env when
    run for real inside intelligence-scheduler.service — see
    /etc/systemd/system/intelligence-scheduler.service, EnvironmentFile=
    platform-runtime/.env only). TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID live in
    platform-runtime/.env, not the repo-root .env, so both are loaded here
    (repo-root first, so its values win on any overlapping key, matching the
    order every multi-file systemd unit in this repo uses).

    2026-08-29: migrated onto core/platform/configuration_service.py's
    load_dotenv_files() (see tools/check_config_loaders.py) — this file
    previously hand-rolled its own copy (unlike heartbeat.py/
    deadmans_switch.py, this drill script has no stated reason to avoid a
    core.* dependency, it's a manually-invoked test tool)."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from core.platform.configuration_service import load_dotenv_files

    load_dotenv_files([_REPO_ROOT / ".env", _REPO_ROOT / "platform-runtime" / ".env"])


_load_dotenv()


def build_drill_event() -> dict[str, Any]:
    """One synthetic `core_events`-shaped dict, shaped exactly like
    `tests/fixtures/synthetic_core_events.py::INTERRUPT_NOW_EVENT` (the same
    fixture this platform's own interrupt_dispatcher tests use), with
    importance/confidence clearly crossing both `interrupt_now` floors
    (90 >= 75, 85 >= 70) and an event_id namespaced `drill-` so it can never
    collide with a real `core_events.event_id`."""
    return {
        "event_id": f"drill-{uuid.uuid4().hex[:12]}",
        # Deliberately hyphenated, not underscored (unlike real domain/
        # event_type values such as "personal_health_intelligence") —
        # interrupt_dispatcher.py's title is f"{domain} · {event_type}",
        # wrapped in *…* by notification_service.py's "alert" template and
        # sent with Telegram legacy parse_mode=Markdown, which treats a bare
        # "_" as an unmatched italic delimiter and 400s the whole send
        # ("can't parse entities"). Confirmed live 2026-08-22 while building
        # this drill: the real pipeline currently 400s for every real
        # interrupt_now event, since every real domain name in
        # tests/fixtures/synthetic_core_events.py (and, per that fixture's
        # own docstring, core_events itself) contains an underscore — a
        # second, independent bug from the "never crosses both floors"
        # finding this drill exists to work around. Not fixed here
        # (notification_service.py / interrupt_dispatcher.py are out of this
        # module's scope) — flagged in this module's own report instead so
        # it isn't silently masked by this workaround.
        "event_type": "attention-engine.drill",
        "domain": "platform-operations",
        "source": "core.platform.attention_drill",
        "importance": 90,
        "confidence": 85,
        "relevance": 100,
        "linked_entities": [],
        "linked_missions": [],
        "linked_documents": [],
        "recommended_action": (
            f"{DRILL_MARKER} This confirms the interrupt-now to Telegram "
            "delivery pipeline is working end-to-end. No action required."
        ),
        "status": "new",
    }


def run_drill(*, dispatch: bool = True) -> dict[str, Any]:
    """Run one synthetic event through the REAL `evaluate_batch()` and,
    unless `dispatch=False`, the REAL `dispatch_interrupt_now()` delivery
    path (a real Telegram send to the Captain's configured chat — that is
    the intended effect, not a mock).

    Returns a dict with the constructed event, the resulting category/reason,
    and (if dispatched) the list of `NotificationResult`s from
    `dispatch_interrupt_now()`.
    """
    from core.platform.attention_engine import AttentionCategory, evaluate_batch
    from core.platform.captain_brief_contract import (
        assemble_captain_brief,
        recommendations_from_events,
    )

    event = build_drill_event()
    log.info(
        "Drill event constructed: event_id=%s importance=%s confidence=%s",
        event["event_id"], event["importance"], event["confidence"],
    )

    decisions = evaluate_batch([event])
    decision = decisions[0]
    log.info(
        "evaluate_batch() classified drill event as: %s — %s",
        decision.category.value, decision.reason,
    )

    result: dict[str, Any] = {
        "event": event,
        "category": decision.category.value,
        "reason": decision.reason,
        "dispatch_results": [],
    }

    if decision.category != AttentionCategory.INTERRUPT_NOW:
        log.error(
            "DRILL FAILED: expected interrupt_now, got %s — the real "
            "AttentionEngine thresholds and this drill's synthetic scores "
            "have drifted apart. Not dispatching.",
            decision.category.value,
        )
        return result

    recs = recommendations_from_events([event])
    brief = assemble_captain_brief(decisions, recommendations=recs)
    if len(brief.interrupt_now) != 1:
        log.error(
            "DRILL FAILED: assemble_captain_brief() did not surface the "
            "drill event in interrupt_now (got %d item(s)). Not dispatching.",
            len(brief.interrupt_now),
        )
        result["category"] = "assembly_mismatch"
        return result

    if not dispatch:
        log.info("--dry-run: skipping the real dispatch_interrupt_now() / Telegram call.")
        return result

    from core.platform.interrupt_dispatcher import dispatch_interrupt_now

    dispatch_results = dispatch_interrupt_now([event], brief.interrupt_now)
    result["dispatch_results"] = dispatch_results

    if not dispatch_results:
        log.warning(
            "dispatch_interrupt_now() returned zero results for a fresh "
            "interrupt_now item — check its status=='new' guard."
        )
    for r in dispatch_results:
        log.info(
            "dispatch_interrupt_now() result: ok=%s transport=%s attempts=%s error=%s",
            r.ok, r.transport.value, r.attempts, r.error,
        )

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Attention Engine drill — fires one synthetic, clearly-[DRILL]-"
            "labelled event through the real evaluate_batch() + "
            "interrupt_dispatcher pipeline to confirm interrupt_now still "
            "reaches the Captain's Telegram end to end."
        )
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Classify only; do not call the real interrupt_dispatcher / send Telegram.",
    )
    args = parser.parse_args()

    result = run_drill(dispatch=not args.dry_run)

    if result["category"] != "interrupt_now":
        log.error("DRILL FAILED — see log above.")
        return 1

    if args.dry_run:
        log.info("DRILL PASSED (dry-run) — classification confirmed interrupt_now.")
        return 0

    dispatched_ok = any(r.ok for r in result["dispatch_results"])
    if dispatched_ok:
        log.info("DRILL PASSED — interrupt_now classified and dispatched to Telegram.")
        return 0

    log.error("DRILL FAILED — classified interrupt_now but dispatch did not succeed. See log above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
