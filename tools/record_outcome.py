#!/usr/bin/env python3
"""
Outcome & Learning Recorder — USS-TJR-MSN-0076 (Outcome & Learning Capture Loop)

CLI for Claude Code / operator use to close the loop after meaningful work:
record WHAT HAPPENED, WHAT WE LEARNED, whether it's REUSABLE, and whether it
could become CONTENT (flagged only — this tool never publishes anything).

Reuses core/knowledge/outcome_capture.py (which reuses the functional Supabase
client and the existing lessons_learned store). Degrades gracefully when
Supabase is unconfigured.

Usage:
    # Record a mission outcome (non-interactive):
    python3 tools/record_outcome.py record \
        --source-type mission --source-id MSN-0075 \
        --title "Enterprise Discovery Assessment" \
        --status worked \
        --summary "Delivered 9 deliverables; closed loop gaps identified" \
        --actual "Assessment merged" --expected "Single view of capabilities" \
        --lesson "Reuse-first survey beats rebuild" \
        --reusable "Parallel discovery sweeps scale well" \
        --content-potential high --content-class linkedin \
        --work --confidence 4 --tag discovery --tag reuse

    # Record a decision outcome:
    python3 tools/record_outcome.py record \
        --source-type decision --source-id D-031 --title "..." --status partial

    # Interactive capture (prompts for the essentials):
    python3 tools/record_outcome.py record

    # Retrieval / review:
    python3 tools/record_outcome.py list-recent
    python3 tools/record_outcome.py list-uncaptured
    python3 tools/record_outcome.py list-lessons
    python3 tools/record_outcome.py list-reusable
    python3 tools/record_outcome.py list-content
    python3 tools/record_outcome.py brief        # the compact learning snapshot

Outcome status: worked | partial | failed | mixed | too_early | abandoned
Content potential: none | low | medium | high
Content class: internal_work | linkedin | coaching | wellness |
               operational_resilience | leadership | personal_learning |
               not_for_publication
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "core" / "knowledge"))

from outcome_capture import (  # type: ignore  # noqa: E402
    OutcomeInput,
    record_outcome,
    list_recent_outcomes,
    list_uncaptured,
    list_lessons,
    list_reusable_insights,
    list_content_worthy,
    learning_brief_snapshot,
    learning_metrics,
    learning_status,
    learning_status_block,
    SOURCE_TYPES,
    OUTCOME_STATUSES,
    CONTENT_POTENTIAL,
    CONTENT_CLASSIFICATIONS,
    is_configured,
)


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------

def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"  {label}{suffix}: ").strip()
    return val or default


def _interactive_record() -> OutcomeInput:
    print("\n── Record an Outcome ────────────────────────────────────────")
    print(f"  source types: {', '.join(SOURCE_TYPES)}")
    source_type = _prompt("Source type", "mission")
    source_id = _prompt("Source ID (e.g. MSN-0075 / D-031)")
    title = _prompt("Title")
    print(f"  status: {', '.join(OUTCOME_STATUSES)}")
    status = _prompt("Outcome status", "worked")
    summary = _prompt("Outcome summary")
    actual = _prompt("Actual result")
    expected = _prompt("Expected result")
    lesson = _prompt("Lesson learned")
    reusable = _prompt("Reusable insight")
    print(f"  content potential: {', '.join(CONTENT_POTENTIAL)}")
    cpot = _prompt("Content potential", "none")
    print(f"  content class: {', '.join(CONTENT_CLASSIFICATIONS)}")
    cclass = _prompt("Content classification", "internal_work")
    conf_raw = _prompt("Confidence 1-5", "")
    confidence = int(conf_raw) if conf_raw.isdigit() and int(conf_raw) in range(1, 6) else None
    return OutcomeInput(
        source_type=source_type, source_id=source_id, title=title,
        outcome_status=status, outcome_summary=summary, actual_result=actual,
        expected_result=expected, lesson_learned=lesson, reusable_insight=reusable,
        content_potential=cpot, content_classification=cclass, confidence=confidence,
    )


def _cmd_record(args) -> int:
    if args.source_id and args.title:
        inp = OutcomeInput(
            source_type=args.source_type,
            source_id=args.source_id,
            title=args.title,
            outcome_status=args.status or "",
            outcome_summary=args.summary or "",
            decision_or_action_taken=args.action_taken or "",
            actual_result=args.actual or "",
            expected_result=args.expected or "",
            variance=args.variance or "",
            lesson_learned=args.lesson or "",
            reusable_insight=args.reusable or "",
            reuse_tags=args.tag or [],
            content_potential=args.content_potential,
            content_classification=args.content_class,
            coaching_relevance=args.coaching,
            work_relevance=args.work,
            confidence=args.confidence,
            evidence_links=args.evidence or [],
            promote_lesson=not args.no_lesson,
        )
    else:
        inp = _interactive_record()

    res = record_outcome(inp)

    for w in res.warnings:
        print(f"  ⚠  {w}")
    if res.errors:
        for e in res.errors:
            print(f"  ❌ {e}")
        return 1

    status = "persisted" if res.persisted else "validated (not persisted — offline)"
    print(f"  ✅ Outcome {res.outcome_id} for {res.source_type} {res.source_id} — {status}")
    if res.lesson_id:
        print(f"     ↳ lesson promoted to lessons_learned as {res.lesson_id}")
    return 0


# ---------------------------------------------------------------------------
# list / brief
# ---------------------------------------------------------------------------

def _offline_note() -> None:
    if not is_configured():
        print("  (Supabase not configured — no records to show.)")


def _cmd_list_recent(args) -> int:
    rows = list_recent_outcomes(limit=args.limit)
    print(f"\n── Recent Outcomes ({len(rows)}) ─────────────────────────────")
    _offline_note()
    for r in rows:
        print(f"  {r.get('outcome_id','?'):<20} {r.get('source_type',''):<14} "
              f"{str(r.get('source_id','')):<14} {r.get('outcome_status') or '-':<10} {r.get('title','')[:50]}")
    return 0


def _cmd_list_uncaptured(args) -> int:
    rows = list_uncaptured(limit=args.limit)
    print(f"\n── Open Items Missing Outcome Capture ({len(rows)}) ──────────")
    _offline_note()
    _TIER = {"learning_debt": "🔴 DEBT(30d+)", "xo": "🟠 XO(21d+)",
             "number_one": "🟠 N1(14d+)", "reminder": "🟡 reminder(7d+)", "none": ""}
    for r in rows:
        tier = _TIER.get(r.get("escalation_tier", "none"), "")
        age = r.get("age_days")
        age_s = f"{age}d" if age is not None else "?"
        print(f"  [{r['source_type']:<8}] {str(r['source_id']):<16} {age_s:>4}  {tier:<14} {r['title'][:44]}")
    if rows:
        print("\n  → Record with: python3 tools/record_outcome.py record "
              "--source-type <t> --source-id <id> --title <...> --status <...>")
    return 0


def _cmd_list_lessons(args) -> int:
    rows = list_lessons(limit=args.limit)
    print(f"\n── Recent Lessons Learned ({len(rows)}) ──────────────────────")
    _offline_note()
    for r in rows:
        print(f"  {r.get('lesson_id','?'):<8} {r.get('date_recorded') or '':<12} {r.get('title','')[:54]}")
        if r.get("future_guidance"):
            print(f"           ↳ {r['future_guidance'][:70]}")
    return 0


def _cmd_list_reusable(args) -> int:
    rows = list_reusable_insights(limit=args.limit)
    print(f"\n── Reusable Insights ({len(rows)}) ───────────────────────────")
    _offline_note()
    for r in rows:
        tags = ", ".join(r.get("reuse_tags") or [])
        print(f"  {r.get('source_type',''):<12} {str(r.get('source_id','')):<14} {r.get('reusable_insight','')[:54]}"
              + (f"  #{tags}" if tags else ""))
    return 0


def _cmd_list_content(args) -> int:
    rows = list_content_worthy(limit=args.limit)
    print(f"\n── Content-Worthy Learnings ({len(rows)}) ────────────────────")
    _offline_note()
    for r in rows:
        print(f"  [{r.get('content_potential',''):<6}] {r.get('content_classification',''):<22} "
              f"{r.get('title','')[:48]}")
    if rows:
        print("\n  → COMMS-001 can consume these later via `/comms`. This tool publishes nothing.")
    return 0


def _cmd_status(args) -> int:
    """MSN-0080: the Captain's Chair LEARNING STATUS block + aging/health."""
    s = learning_status()
    print()
    # Reuse the canonical block, then add aging detail.
    block = learning_status_block().replace("*", "")  # plain for CLI
    print(block)
    if s.data_available:
        print(f"\n  Aging — GREEN(0-7): {s.pending_green}  "
              f"AMBER(8-14): {s.pending_amber}  RED(15+): {s.pending_red}")
        if s.outcomes_per_week:
            print("  Outcomes/week (recent→older): " +
                  " ".join(str(n) for n in s.outcomes_per_week))
        if s.health_reasons:
            print("  Health basis: " + "; ".join(s.health_reasons))
    return 0


def _cmd_metrics(args) -> int:
    m = learning_metrics()
    print("\n── Learning Metrics ──────────────────────────────────────────")
    if not m.data_available:
        print("  (Supabase not configured — metrics unavailable.)")
        return 0
    for k, v in m.as_dict().items():
        print(f"  {k:<26} {v}")
    return 0


def _cmd_brief(args) -> int:
    snap = learning_brief_snapshot()
    print("\n── Learning & Outcome Snapshot ───────────────────────────────")
    if not snap.data_available:
        print("  (Supabase not configured — snapshot unavailable.)")
        return 0
    print(f"  Recent lessons:        {len(snap.recent_lessons)}")
    print(f"  Missing outcomes:      {snap.uncaptured_count}")
    print(f"  Reusable insights:     {snap.reusable_count}")
    print(f"  Content-worthy:        {snap.content_worthy_count}")
    for r in snap.recent_lessons:
        print(f"    • {r.get('lesson_id','?')}: {r.get('title','')[:60]}")
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Record and review outcomes & learning (MSN-0076)")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("record", help="Record an outcome (interactive if --source-id/--title omitted)")
    r.add_argument("--source-type", choices=SOURCE_TYPES, default="mission")
    r.add_argument("--source-id")
    r.add_argument("--title")
    r.add_argument("--status", choices=OUTCOME_STATUSES)
    r.add_argument("--summary")
    r.add_argument("--action-taken")
    r.add_argument("--actual")
    r.add_argument("--expected")
    r.add_argument("--variance")
    r.add_argument("--lesson")
    r.add_argument("--reusable")
    r.add_argument("--tag", action="append", help="Reuse tag (repeatable)")
    r.add_argument("--content-potential", choices=CONTENT_POTENTIAL, default="none")
    r.add_argument("--content-class", choices=CONTENT_CLASSIFICATIONS, default="internal_work")
    r.add_argument("--coaching", action="store_true", help="Mark coaching-relevant")
    r.add_argument("--work", action="store_true", help="Mark work-relevant")
    r.add_argument("--confidence", type=int, choices=[1, 2, 3, 4, 5])
    r.add_argument("--evidence", action="append", help="Evidence link (repeatable)")
    r.add_argument("--no-lesson", action="store_true",
                   help="Do not promote lesson_learned into lessons_learned")
    r.set_defaults(func=_cmd_record)

    for name, fn, help_ in [
        ("list-recent", _cmd_list_recent, "List recent outcome records"),
        ("list-uncaptured", _cmd_list_uncaptured, "List closed missions/decisions missing outcomes"),
        ("list-lessons", _cmd_list_lessons, "List recent lessons learned"),
        ("list-reusable", _cmd_list_reusable, "List reusable insights"),
        ("list-content", _cmd_list_content, "List content-worthy learnings"),
        ("brief", _cmd_brief, "Show the compact learning/outcome snapshot"),
        ("metrics", _cmd_metrics, "Show learning metrics (counts)"),
        ("status", _cmd_status, "Show the LEARNING STATUS block (aging + health)"),
    ]:
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--limit", type=int, default=10)
        sp.set_defaults(func=fn)

    args = p.parse_args()
    if not getattr(args, "cmd", None):
        p.print_help()
        sys.exit(0)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
