"""Strategic Pattern Detection (EXEC-010C WP9).

Analyses intelligence_notes corpus to surface recurring concerns, emerging
themes, and abandoned ideas. Used by WP8 (XO synthesis) and WP10 (Captain's
Chair dashboard).

Public API:
    detect_patterns(supabase_client, lookback_days=30) -> PatternReport
    format_pattern_report(report: PatternReport) -> str
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger(__name__)

_THEME_KEYWORDS: dict[str, list[str]] = {
    "capability_gaps":    ["gap", "missing", "lack", "need", "capability", "unable", "can't", "cannot"],
    "architecture":       ["architecture", "design", "structure", "pattern", "refactor", "technical debt", "adr"],
    "delivery":           ["ship", "release", "deploy", "delivery", "sprint", "velocity", "pipeline"],
    "strategy":           ["strategy", "objective", "goal", "vision", "direction", "priority", "roadmap"],
    "operations":         ["operations", "runbook", "incident", "alert", "monitoring", "reliability"],
    "knowledge_capture":  ["document", "knowledge", "learn", "lesson", "capture", "record", "write up"],
    "people":             ["team", "hire", "resource", "officer", "crew", "skill", "training"],
    "communication":      ["comms", "communicate", "announce", "share", "update", "brief"],
}


@dataclass
class ThemeCluster:
    theme: str
    count: int
    note_ids: list[str] = field(default_factory=list)
    representative_titles: list[str] = field(default_factory=list)


@dataclass
class RecurringConcern:
    topic: str
    frequency: int
    first_seen: str
    last_seen: str
    note_ids: list[str] = field(default_factory=list)


@dataclass
class AbandonedIdea:
    note_id: str
    title: str
    captured_at: str
    days_stalled: int
    last_status: str


@dataclass
class PatternReport:
    emerging_themes: list[ThemeCluster] = field(default_factory=list)
    recurring_concerns: list[RecurringConcern] = field(default_factory=list)
    abandoned_ideas: list[AbandonedIdea] = field(default_factory=list)
    domain_distribution: dict[str, int] = field(default_factory=dict)
    total_notes_analysed: int = 0
    lookback_days: int = 30
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def has_signals(self) -> bool:
        return bool(self.emerging_themes or self.recurring_concerns or self.abandoned_ideas)

    @property
    def top_theme(self) -> ThemeCluster | None:
        return self.emerging_themes[0] if self.emerging_themes else None


def _classify_themes(text: str) -> list[str]:
    text_lower = text.lower()
    matched = []
    for theme, keywords in _THEME_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            matched.append(theme)
    return matched


def detect_patterns(
    supabase_client: Any,
    lookback_days: int = 30,
) -> PatternReport:
    """Analyse notes corpus for recurring concerns, emerging themes, abandoned ideas."""
    report = PatternReport(lookback_days=lookback_days)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()

    try:
        result = supabase_client.table("intelligence_notes").select(
            "id, title, raw_content, classification, status, recommended_route, "
            "created_at, updated_at, strategic_alignment_score, triage_summary"
        ).gte("created_at", cutoff).not_.in_("status", ["ARCHIVED"]).execute()
    except Exception as exc:
        log.warning("[notebook-patterns] Failed to fetch notes: %s", exc)
        return report

    notes: list[dict[str, Any]] = result.data or []
    report.total_notes_analysed = len(notes)

    if not notes:
        return report

    # Emerging themes
    theme_buckets: dict[str, list[dict]] = defaultdict(list)
    for note in notes:
        combined = f"{note.get('title', '')} {note.get('raw_content', '')} {note.get('triage_summary', '')}"
        for theme in _classify_themes(combined):
            theme_buckets[theme].append(note)

    report.emerging_themes = sorted(
        [
            ThemeCluster(
                theme=theme,
                count=len(bucket_notes),
                note_ids=[n["id"] for n in bucket_notes[:10]],
                representative_titles=[
                    (n.get("title") or n.get("raw_content", "")[:60])
                    for n in sorted(bucket_notes, key=lambda x: x.get("strategic_alignment_score") or 0, reverse=True)[:3]
                ],
            )
            for theme, bucket_notes in theme_buckets.items()
        ],
        key=lambda t: t.count,
        reverse=True,
    )

    # Recurring concerns — classification-level repetition
    classification_counts: Counter = Counter()
    classification_notes: dict[str, list[dict]] = defaultdict(list)
    for note in notes:
        cls = note.get("classification")
        if cls:
            classification_counts[cls] += 1
            classification_notes[cls].append(note)

    for cls, count in classification_counts.most_common(5):
        if count < 2:
            continue
        cls_notes = sorted(classification_notes[cls], key=lambda x: x["created_at"])
        report.recurring_concerns.append(RecurringConcern(
            topic=cls,
            frequency=count,
            first_seen=cls_notes[0]["created_at"],
            last_seen=cls_notes[-1]["created_at"],
            note_ids=[n["id"] for n in cls_notes[:10]],
        ))

    # Abandoned ideas — CAPTURED/OFFICER_REVIEW stalled >7 days
    now = datetime.now(timezone.utc)
    for note in notes:
        if note["status"] not in ("CAPTURED", "OFFICER_REVIEW"):
            continue
        try:
            created = datetime.fromisoformat(note["created_at"].replace("Z", "+00:00"))
            days_stalled = (now - created).days
        except Exception:
            continue
        if days_stalled >= 7:
            report.abandoned_ideas.append(AbandonedIdea(
                note_id=note["id"],
                title=note.get("title") or note.get("raw_content", "")[:60],
                captured_at=note["created_at"],
                days_stalled=days_stalled,
                last_status=note["status"],
            ))

    report.abandoned_ideas.sort(key=lambda x: x.days_stalled, reverse=True)

    # Domain distribution from recommended_route
    route_counts: Counter = Counter(
        note.get("recommended_route") or "unrouted"
        for note in notes
    )
    report.domain_distribution = dict(route_counts.most_common())

    log.info(
        "[notebook-patterns] Analysed %d notes: %d themes, %d concerns, %d stalled",
        len(notes),
        len(report.emerging_themes),
        len(report.recurring_concerns),
        len(report.abandoned_ideas),
    )
    return report


def format_pattern_report(report: PatternReport) -> str:
    """Format pattern report as a Slack-ready summary block."""
    if not report.has_signals:
        return ""

    lines: list[str] = [
        "*Strategic Pattern Analysis*",
        f"_Last {report.lookback_days} days — {report.total_notes_analysed} notes_",
        "",
    ]

    if report.emerging_themes:
        top = report.emerging_themes[:3]
        lines.append("*Emerging Themes:*")
        for t in top:
            lines.append(f"  :small_blue_diamond: {t.theme.replace('_', ' ').title()} ({t.count} notes)")
        lines.append("")

    if report.recurring_concerns:
        lines.append("*Recurring Concerns:*")
        for rc in report.recurring_concerns[:3]:
            lines.append(f"  :repeat: {rc.topic} — {rc.frequency}×")
        lines.append("")

    if report.abandoned_ideas:
        stalled_count = len(report.abandoned_ideas)
        oldest = report.abandoned_ideas[0]
        lines.append(f"*Stalled Ideas:* {stalled_count} ({oldest.days_stalled}d oldest)")

    return "\n".join(lines)


__all__ = [
    "PatternReport",
    "ThemeCluster",
    "RecurringConcern",
    "AbandonedIdea",
    "detect_patterns",
    "format_pattern_report",
]
