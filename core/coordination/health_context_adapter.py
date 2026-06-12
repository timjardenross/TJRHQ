"""
Health Context Adapter — WP3

Transforms memory/Health-Summary.md into a HealthContextPackage.

Design principles:
  - Summary level only (no raw clinical data)
  - No diagnoses or treatment recommendations
  - Safe defaults: missing data → mark as unknown, not assumed
  - Privacy-first: no sensitive detail in command context
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

# Allow importing from context-assembly sibling package
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "context-assembly"))

from models import HealthContextPackage, HealthStatusSnapshot, HealthTrendSummary


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------

def parse_health_summary(path: Path) -> Dict[str, Any]:
    """
    Read and parse Health Summary markdown into structured dict.

    Returns a dict with keys:
      themes, recovery_priorities, tracking_domains,
      standing_context, medical_officer_rules,
      weekly_reflection, frontmatter
    """
    if not path.exists():
        return _empty_summary(str(path))

    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    result: Dict[str, Any] = {
        "source_file": str(path),
        "frontmatter": {},
        "themes": [],
        "recovery_priorities": [],
        "tracking_domains": {},
        "standing_context": {},
        "medical_officer_rules": [],
        "weekly_reflection": {},
    }

    # Parse YAML frontmatter
    result["frontmatter"] = _parse_frontmatter(lines)

    # Parse sections by heading
    sections = _split_sections(raw)
    result["themes"] = _parse_themes(sections)
    result["recovery_priorities"] = _parse_recovery_priorities(sections)
    result["weekly_reflection"] = _parse_weekly_reflection(sections)

    return result


def extract_trends(summary_dict: Dict[str, Any]) -> HealthTrendSummary:
    """
    Derive trend direction from weekly reflection data.

    Pain/energy trends are inferred from the reflection section if filled in.
    Returns unknown if no data available (safe default).
    """
    reflection = summary_dict.get("weekly_reflection", {})

    pain_trend = _infer_trend(reflection.get("pain_trend_text", ""))
    energy_trend = _infer_trend(reflection.get("energy_trend_text", ""))

    # Overall direction: worse of pain and energy
    trend_rank = {"improving": 0, "stable": 1, "worsening": 2, "unknown": 3}
    trends = [t for t in [pain_trend, energy_trend] if t != "unknown"]
    if trends:
        overall = max(trends, key=lambda t: trend_rank.get(t, 3))
    else:
        overall = "unknown"

    return HealthTrendSummary(
        pain_trend=pain_trend,
        energy_trend=energy_trend,
        overall_direction=overall,
    )


def build_health_context(summary_dict: Dict[str, Any], timestamp: Optional[str] = None) -> HealthContextPackage:
    """
    Assemble HealthContextPackage from parsed summary dict.

    Always returns a valid package — missing fields default to None/unknown.
    """
    assembled_at = timestamp or (datetime.utcnow().isoformat() + "Z")

    reflection = summary_dict.get("weekly_reflection", {})
    trend = extract_trends(summary_dict)

    # Determine data quality
    has_reflection_data = any([
        reflection.get("pain_avg"),
        reflection.get("mood_overall"),
        reflection.get("energy_overall"),
    ])
    data_quality = "partial" if has_reflection_data else "missing"
    if has_reflection_data and reflection.get("week_date"):
        data_quality = "complete"

    # Status snapshot — only include if present in reflection
    status = HealthStatusSnapshot(
        pain_level=_normalise_pain(reflection.get("pain_avg")),
        mood=_normalise_level(reflection.get("mood_overall")),
        energy=_normalise_level(reflection.get("energy_overall")),
        stress=_normalise_level(reflection.get("stress_overall")),
        sleep_quality=_normalise_sleep(reflection.get("sleep_notes")),
    )

    # Workload constraint: if pain is high or energy is low → reduced
    workload = _derive_workload_constraint(status)

    # Medical Officer note: surface recovery priorities as advisory note
    priorities = summary_dict.get("recovery_priorities", [])
    mo_note = f"Recovery focus: {'; '.join(priorities[:3])}" if priorities else None

    # Safety flags: none at summary level unless explicitly documented
    safety_flags: List[str] = []

    return HealthContextPackage(
        assembled_at=assembled_at,
        source_file=summary_dict.get("source_file", ""),
        status_summary=status,
        trend_summary=trend,
        recovery_priorities=priorities,
        health_themes=summary_dict.get("themes", []),
        medical_officer_note=mo_note,
        safety_flags=safety_flags,
        workload_constraint=workload,
        data_quality=data_quality,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _empty_summary(path: str) -> Dict[str, Any]:
    return {
        "source_file": path,
        "frontmatter": {},
        "themes": [],
        "recovery_priorities": [],
        "tracking_domains": {},
        "standing_context": {},
        "medical_officer_rules": [],
        "weekly_reflection": {},
    }


def _parse_frontmatter(lines: List[str]) -> Dict[str, str]:
    if not lines or lines[0].strip() != "---":
        return {}
    fm: Dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def _split_sections(raw: str) -> Dict[str, str]:
    """Split markdown into sections keyed by heading text."""
    sections: Dict[str, str] = {}
    current_heading = "_preamble"
    current_lines: List[str] = []

    for line in raw.splitlines():
        m = re.match(r"^#{1,3}\s+(.+)$", line)
        if m:
            sections[current_heading] = "\n".join(current_lines)
            current_heading = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    sections[current_heading] = "\n".join(current_lines)
    return sections


def _parse_themes(sections: Dict[str, str]) -> List[str]:
    for heading, body in sections.items():
        if "health theme" in heading.lower() or "current health theme" in heading.lower():
            return [
                line.lstrip("- •").strip()
                for line in body.splitlines()
                if line.strip().startswith(("-", "•")) and line.strip()[2:]
            ]
    return []


def _parse_recovery_priorities(sections: Dict[str, str]) -> List[str]:
    for heading, body in sections.items():
        if "recovery priorit" in heading.lower():
            items = []
            for line in body.splitlines():
                m = re.match(r"^\d+\.\s+(.+)$", line.strip())
                if m:
                    items.append(m.group(1).strip())
                elif line.strip().startswith(("-", "•")):
                    items.append(line.lstrip("- •").strip())
            return items
    return []


def _parse_weekly_reflection(sections: Dict[str, str]) -> Dict[str, Any]:
    """
    Extract filled-in data from the Weekly Health Reflection Template.

    Because _split_sections splits on all heading levels (## and ###), the
    sub-sections of the Weekly Reflection template appear as top-level keys
    in the sections dict. We look for all reflection-related keys directly.
    """
    reflection: Dict[str, Any] = {}

    for heading, body in sections.items():
        sh = heading.lower()
        text = body.strip()

        if "week commencing" in sh:
            date_m = re.search(r"\d{4}-\d{2}-\d{2}", text)
            if date_m:
                reflection["week_date"] = date_m.group(0)

        elif "pain trend" in sh:
            reflection["pain_trend_text"] = text
            avg_m = re.search(r"average[:\s]+(.+)", text, re.IGNORECASE)
            if avg_m:
                val = avg_m.group(1).strip()
                if val:
                    reflection["pain_avg"] = val

        elif "mood trend" in sh:
            reflection["mood_trend_text"] = text
            overall_m = re.search(r"overall[:\s]+(.+)", text, re.IGNORECASE)
            if overall_m:
                val = overall_m.group(1).strip()
                if val:
                    reflection["mood_overall"] = val

        elif "energy trend" in sh:
            reflection["energy_trend_text"] = text
            overall_m = re.search(r"overall[:\s]+(.+)", text, re.IGNORECASE)
            if overall_m:
                val = overall_m.group(1).strip()
                if val:
                    reflection["energy_overall"] = val

        elif "stress trend" in sh:
            reflection["stress_trend_text"] = text
            overall_m = re.search(r"overall[:\s]+(.+)", text, re.IGNORECASE)
            if overall_m:
                val = overall_m.group(1).strip()
                if val:
                    reflection["stress_overall"] = val

        elif "what helped" in sh:
            items = [
                line.lstrip("- •").strip()
                for line in text.splitlines()
                if line.strip().startswith(("-", "•")) and len(line.strip()) > 2
            ]
            if items:
                reflection["what_helped"] = items

        elif "what made" in sh or "made things worse" in sh:
            items = [
                line.lstrip("- •").strip()
                for line in text.splitlines()
                if line.strip().startswith(("-", "•")) and len(line.strip()) > 2
            ]
            if items:
                reflection["what_worsened"] = items

    return reflection


def _infer_trend(text: str) -> str:
    """Map free text to improving/stable/worsening/unknown."""
    if not text:
        return "unknown"
    t = text.lower()
    if any(w in t for w in ("improv", "better", "less pain", "higher energy", "good")):
        return "improving"
    if any(w in t for w in ("worsen", "worse", "increas", "higher pain", "flare", "low energy")):
        return "worsening"
    if any(w in t for w in ("stable", "same", "unchanged", "consistent")):
        return "stable"
    return "unknown"


def _normalise_pain(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.lower()
    # Try to detect numeric score
    m = re.search(r"\b([0-9]|10)\b", v)
    if m:
        score = int(m.group(1))
        if score <= 3:
            return "low"
        if score <= 6:
            return "moderate"
        return "high"
    if any(w in v for w in ("low", "mild", "minimal")):
        return "low"
    if any(w in v for w in ("moderate", "medium")):
        return "moderate"
    if any(w in v for w in ("high", "severe", "intense")):
        return "high"
    return value[:50]


def _normalise_level(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.lower()
    if any(w in v for w in ("low", "poor", "bad", "down")):
        return "low"
    if any(w in v for w in ("stable", "moderate", "okay", "ok", "neutral", "fair")):
        return "stable"
    if any(w in v for w in ("high", "good", "positive", "great", "excellent")):
        return "positive"
    return None


def _normalise_sleep(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.lower()
    if any(w in v for w in ("poor", "bad", "disturb", "broken", "little")):
        return "poor"
    if any(w in v for w in ("fair", "okay", "moderate")):
        return "fair"
    if any(w in v for w in ("good", "great", "restful", "well")):
        return "good"
    return None


def _derive_workload_constraint(status: HealthStatusSnapshot) -> str:
    if status.pain_level == "high" or status.energy == "low":
        return "reduced"
    if status.pain_level is None and status.energy is None:
        return "unknown"
    return "normal"
