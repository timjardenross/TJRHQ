"""
Lessons Learned Intelligence Analyser — WP3 / Sprint C (G-011)

Parses knowledge/Lessons-Learned.md and mission-outcomes.jsonl to:
  - Extract structured lesson records
  - Identify recurring success patterns
  - Identify recurring failure patterns
  - Surface reusable patterns for the Knowledge Officer

Usage:
    from core.knowledge.lessons_analyser import analyse_lessons
    result = analyse_lessons()
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger(__name__)

_LESSONS_PATH = _REPO_ROOT / "knowledge" / "Lessons-Learned.md"
_OUTCOMES_PATH = _REPO_ROOT / "knowledge" / "mission-outcomes.jsonl"

MIN_LESSONS_FOR_PATTERN = 3


def _parse_lessons_md(path: Path) -> List[Dict[str, Any]]:
    """Parse Lessons-Learned.md into structured lesson records."""
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    lessons: List[Dict[str, Any]] = []

    # Split on LL-NNN headings
    blocks = re.split(r"\n## (LL-\d+)\n", text)
    # blocks = [preamble, 'LL-001', content1, 'LL-002', content2, ...]
    i = 1
    while i < len(blocks) - 1:
        ll_id = blocks[i]
        content = blocks[i + 1]
        i += 2

        lesson: Dict[str, Any] = {"id": ll_id, "raw": content.strip()}

        # Extract Title
        title_m = re.search(r"### Title\s*\n+(.+)", content)
        lesson["title"] = title_m.group(1).strip() if title_m else ""

        # Extract Date
        date_m = re.search(r"### Date\s*\n+(.+)", content)
        lesson["date"] = date_m.group(1).strip() if date_m else ""

        # Extract Lesson body
        lesson_m = re.search(r"### Lesson\s*\n+(.*?)(?=\n###|\Z)", content, re.DOTALL)
        lesson["lesson"] = lesson_m.group(1).strip() if lesson_m else ""

        # Extract Future Guidance
        guidance_m = re.search(r"### Future Guidance\s*\n+(.*?)(?=\n###|\n---|\Z)", content, re.DOTALL)
        lesson["future_guidance"] = guidance_m.group(1).strip() if guidance_m else ""

        if lesson["title"]:
            lessons.append(lesson)

    return lessons


def _load_outcomes(path: Path) -> List[Dict[str, Any]]:
    """Load mission-outcomes.jsonl records."""
    if not path.exists():
        return []
    outcomes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                outcomes.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return outcomes


def _extract_themes(lessons: List[Dict]) -> Dict[str, int]:
    """Simple keyword frequency across lesson texts."""
    stopwords = {
        "the", "a", "an", "and", "or", "in", "on", "to", "for", "of", "with",
        "is", "are", "was", "be", "been", "have", "before", "after", "always",
        "that", "this", "it", "when", "by", "from", "as", "at", "not", "no",
    }
    words: List[str] = []
    for l in lessons:
        text = f"{l.get('lesson', '')} {l.get('future_guidance', '')}"
        tokens = re.findall(r"\b[a-z]{4,}\b", text.lower())
        words.extend(t for t in tokens if t not in stopwords)
    return dict(Counter(words).most_common(20))


def analyse_lessons() -> Dict[str, Any]:
    """
    Analyse lessons learned and mission outcomes for patterns.

    Returns:
        lessons:                List of parsed lesson dicts
        total_lessons:          int
        outcomes:               List of mission outcome dicts
        total_outcomes:         int
        recurring_themes:       {word: count} top-20 keywords
        success_patterns:       List[str] — lessons tagged as positive
        failure_patterns:       List[str] — lessons about avoiding mistakes
        reusable_patterns:      List[str] — future guidance extracts
        outcome_avg_score:      float or None
        outcome_has_pattern_pct: float — % of outcomes with a reusable pattern
        findings:               List[str]
        status:                 'ok' | 'insufficient_data'
    """
    lessons  = _parse_lessons_md(_LESSONS_PATH)
    outcomes = _load_outcomes(_OUTCOMES_PATH)

    if not lessons:
        return {
            "lessons": [], "total_lessons": 0,
            "outcomes": outcomes, "total_outcomes": len(outcomes),
            "recurring_themes": {}, "success_patterns": [],
            "failure_patterns": [], "reusable_patterns": [],
            "outcome_avg_score": None, "outcome_has_pattern_pct": None,
            "findings": ["No lessons found in Lessons-Learned.md."],
            "status": "insufficient_data",
        }

    # Classify lessons as success vs. failure pattern by keyword heuristic
    failure_kw = {"mistake", "failed", "avoid", "problem", "issue", "broken",
                  "wrong", "error", "risk", "debt", "incomplete", "premature"}
    success_kw = {"proven", "effective", "success", "value", "improve",
                  "better", "foundation", "correct", "robust", "reliable"}

    success_patterns: List[str] = []
    failure_patterns: List[str] = []
    reusable_patterns: List[str] = []

    for l in lessons:
        text = (l.get("lesson", "") + " " + l.get("future_guidance", "")).lower()
        title = l.get("title", "")
        guidance = l.get("future_guidance", "")

        if any(kw in text for kw in failure_kw):
            failure_patterns.append(f"[{l['id']}] {title}")
        if any(kw in text for kw in success_kw):
            success_patterns.append(f"[{l['id']}] {title}")
        if guidance:
            reusable_patterns.append(f"[{l['id']}] {guidance[:120]}")

    # Outcome stats
    outcome_scores = [o.get("outcome_score") for o in outcomes if o.get("outcome_score") is not None]
    outcome_avg = round(sum(outcome_scores) / len(outcome_scores), 2) if outcome_scores else None
    pattern_count = sum(1 for o in outcomes if o.get("has_pattern"))
    pattern_pct = round(pattern_count / len(outcomes) * 100) if outcomes else None

    recurring_themes = _extract_themes(lessons)
    top_themes = list(recurring_themes.keys())[:5]

    findings: List[str] = [
        f"Lessons library: {len(lessons)} lessons recorded ({len(success_patterns)} success, "
        f"{len(failure_patterns)} failure patterns)."
    ]
    if top_themes:
        findings.append(f"Recurring themes across lessons: {', '.join(top_themes)}.")
    if outcome_avg is not None:
        findings.append(f"Mission outcomes: {len(outcomes)} records, avg score {outcome_avg}/1.0.")
    if pattern_pct is not None:
        findings.append(f"{pattern_pct}% of recorded outcomes include a reusable pattern.")

    status = "ok" if len(lessons) >= MIN_LESSONS_FOR_PATTERN else "insufficient_data"

    return {
        "lessons":                lessons,
        "total_lessons":          len(lessons),
        "outcomes":               outcomes,
        "total_outcomes":         len(outcomes),
        "recurring_themes":       recurring_themes,
        "success_patterns":       success_patterns,
        "failure_patterns":       failure_patterns,
        "reusable_patterns":      reusable_patterns,
        "outcome_avg_score":      outcome_avg,
        "outcome_has_pattern_pct": pattern_pct,
        "findings":               findings,
        "status":                 status,
    }
