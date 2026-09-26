"""
Health Context Adapter — WP3 + WP1 (Health Intelligence Uplift)

Primary path: reads live data from captains_log_entries (Supabase).
Legacy fallback: reads Health-Summary.md if Supabase unavailable.

Design principles:
  - Summary level only (no raw clinical data)
  - No diagnoses or treatment recommendations
  - Safe defaults: missing data → mark as unknown, not assumed
  - Privacy-first: no sensitive detail in command context
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow importing from context-assembly sibling package
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "context-assembly"))

from models import HealthContextPackage, HealthStatusSnapshot, HealthTrendSummary


# Lazy import to avoid circular deps and missing-dep errors at import time
def _get_captains_log_live():
    """Try to import the live Supabase path. Returns None if unavailable."""
    try:
        _HEALTH_ROOT = Path(__file__).resolve().parents[2] / "core" / "health"
        if str(_HEALTH_ROOT) not in sys.path:
            sys.path.insert(0, str(_HEALTH_ROOT))
        from capacity_score import compute_capacity_score
        from supabase_client import is_configured, supabase_get
        return supabase_get, is_configured, compute_capacity_score
    except Exception:  # noqa: BLE001 - optional health-module import; (None, None, None) signals unavailability to the caller
        return None, None, None


def _get_capacity_checkin_live():
    """Mission 2 (USS-TJR-MSN-2) fix: capacity_checkins is the platform's
    canonical capacity source (MY CAPACITY TODAY, 2026-08-21) -- this
    adapter was still deriving capacity_score/capacity_status from
    captains_log_entries via a weighted pain/energy/sleep formula
    (compute_capacity_score), a second, competing capacity derivation that
    could disagree with the Captain's own direct capacity_checkins
    self-report. captains_log_entries stays the source for every OTHER
    field here (pain/mood/energy/themes/priorities) -- those are a
    genuinely different domain (a daily journal), not a capacity
    duplication, and are untouched by this fix."""
    try:
        _HEALTH_ROOT = Path(__file__).resolve().parents[2] / "core" / "health"
        if str(_HEALTH_ROOT) not in sys.path:
            sys.path.insert(0, str(_HEALTH_ROOT))
        from capacity_score import capacity_zone_from_checkin
        from supabase_client import is_configured, supabase_get
        return supabase_get, is_configured, capacity_zone_from_checkin
    except Exception:  # noqa: BLE001 - optional health-module import; (None, None, None) signals unavailability to the caller
        return None, None, None


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------

def parse_health_summary(path: Path) -> dict[str, Any]:
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

    result: dict[str, Any] = {
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


def extract_trends(summary_dict: dict[str, Any]) -> HealthTrendSummary:
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


def build_health_context(summary_dict: dict[str, Any], timestamp: str | None = None) -> HealthContextPackage:
    """
    Assemble HealthContextPackage from parsed summary dict.

    Always returns a valid package — missing fields default to None/unknown.
    """
    assembled_at = timestamp or (datetime.now(timezone.utc).isoformat())

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
    safety_flags: list[str] = []

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

def _empty_summary(path: str) -> dict[str, Any]:
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


def _parse_frontmatter(lines: list[str]) -> dict[str, str]:
    if not lines or lines[0].strip() != "---":
        return {}
    fm: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def _split_sections(raw: str) -> dict[str, str]:
    """Split markdown into sections keyed by heading text."""
    sections: dict[str, str] = {}
    current_heading = "_preamble"
    current_lines: list[str] = []

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


def _parse_themes(sections: dict[str, str]) -> list[str]:
    for heading, body in sections.items():
        if "health theme" in heading.lower() or "current health theme" in heading.lower():
            return [
                line.lstrip("- •").strip()
                for line in body.splitlines()
                if line.strip().startswith(("-", "•")) and line.strip()[2:]
            ]
    return []


def _parse_recovery_priorities(sections: dict[str, str]) -> list[str]:
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


def _parse_weekly_reflection(sections: dict[str, str]) -> dict[str, Any]:
    """
    Extract filled-in data from the Weekly Health Reflection Template.

    Because _split_sections splits on all heading levels (## and ###), the
    sub-sections of the Weekly Reflection template appear as top-level keys
    in the sections dict. We look for all reflection-related keys directly.
    """
    reflection: dict[str, Any] = {}

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


def _normalise_pain(value: str | None) -> str | None:
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


def _normalise_level(value: str | None) -> str | None:
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


def _normalise_sleep(value: str | None) -> str | None:
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


# ---------------------------------------------------------------------------
# Live Supabase path (WP1 — primary source)
# ---------------------------------------------------------------------------

def _normalise_energy(val: str | None) -> str | None:
    """Captain's Log uses Title Case; models expect lowercase."""
    if not val:
        return None
    return val.lower()  # Low→low, Moderate→moderate, High→high


def _normalise_mood(val: str | None) -> str | None:
    """Captain's Log: Low/Stable/Positive → low/stable/positive."""
    if not val:
        return None
    return val.lower()


def _normalise_sleep_quality(val: str | None) -> str | None:
    """Captain's Log: Poor/Fair/Good → poor/fair/good."""
    if not val:
        return None
    return val.lower()


def _pain_score_to_level(score: int | None) -> str | None:
    if score is None:
        return None
    if score <= 3:
        return "low"
    if score <= 6:
        return "moderate"
    return "high"


def build_health_context_from_captains_log(
    entry: dict[str, Any] | None,
    trend_direction: str | None = None,
    capacity_score: int | None = None,
    assembled_at: str | None = None,
    energy_trend: str | None = None,
) -> HealthContextPackage:
    """
    Build a HealthContextPackage from a captains_log_entries row.

    entry           — today's or latest Captain's Log row (may be None)
    trend_direction — pre-computed pain trend (improving/stable/worsening)
    capacity_score  — pre-computed capacity score (0–100)
    """
    assembled = assembled_at or (datetime.now(timezone.utc).isoformat())

    if not entry:
        # Mission 2 (USS-TJR-MSN-2) fix: capacity_score is independent of
        # captains_log_entries now (it comes from capacity_checkins) -- a
        # missing/no-today captain's-log row must not also discard a
        # perfectly valid capacity_checkins reading passed in above.
        from capacity_score import capacity_status_only
        return HealthContextPackage(
            assembled_at=assembled,
            source_file="supabase:captains_log_entries",
            data_quality="missing",
            capacity_score=capacity_score,
            capacity_status=capacity_status_only(capacity_score),
        )

    pain_level = _pain_score_to_level(entry.get("pain_score"))
    energy = _normalise_energy(entry.get("energy"))
    mood = _normalise_mood(entry.get("mood"))
    sleep_quality = _normalise_sleep_quality(entry.get("sleep_quality"))

    status = HealthStatusSnapshot(
        pain_level=pain_level,
        mood=mood,
        energy=energy,
        sleep_quality=sleep_quality,
        stress=None,  # not captured in Captain's Log
    )

    _resolved_energy = energy_trend or trend_direction or "unknown"
    trend = HealthTrendSummary(
        pain_trend=trend_direction or "unknown",
        energy_trend=_resolved_energy,
        overall_direction=trend_direction or "unknown",
    )

    workload = _derive_workload_constraint(status)

    # Build themes from what_changed and blockers (non-null, non-empty)
    themes: list[str] = []
    if entry.get("what_changed"):
        themes.append(entry["what_changed"][:120])
    if entry.get("blockers"):
        themes.append(f"Blockers: {entry['blockers'][:80]}")

    # Recovery priorities from wins (positive signal)
    priorities: list[str] = []
    if entry.get("tomorrows_priority"):
        priorities.append(f"Tomorrow: {entry['tomorrows_priority']}")
    if entry.get("wins"):
        priorities.append(f"Recent win: {entry['wins'][:80]}")

    # Mission 2 (USS-TJR-MSN-2) fix: capacity_status_only(None) already
    # returns "Unknown" -- gating this call behind `capacity_score is not
    # None` left cap_status as a bare None instead, contradicting this
    # package's own capacity_status field comment ("Green | Amber | Red |
    # Unknown") and hiding "no signal" from callers that check for the
    # string rather than None (e.g. equality checks against "Unknown").
    from capacity_score import capacity_status_only
    cap_status = capacity_status_only(capacity_score)
    mo_note_parts = []
    if capacity_score is not None:
        mo_note_parts.append(f"Capacity {capacity_score}% ({cap_status})")
    if entry.get("overall_note"):
        mo_note_parts.append(entry["overall_note"][:100])
    mo_note = " | ".join(mo_note_parts) if mo_note_parts else None

    data_quality = "complete" if all([
        entry.get("pain_score") is not None,
        entry.get("energy"),
        entry.get("mood"),
    ]) else "partial"

    return HealthContextPackage(
        assembled_at=assembled,
        source_file="supabase:captains_log_entries",
        status_summary=status,
        trend_summary=trend,
        recovery_priorities=priorities,
        health_themes=themes,
        medical_officer_note=mo_note,
        safety_flags=[],
        workload_constraint=workload,
        capacity_score=capacity_score,
        capacity_status=cap_status,
        data_quality=data_quality,
    )


def build_health_context_live(assembled_at: str | None = None) -> HealthContextPackage:
    """
    Primary entry point (WP1).

    Tries to read live data from captains_log_entries.
    Falls back to legacy Health-Summary.md path if Supabase unavailable.

    Capacity score/status (Mission 2, USS-TJR-MSN-2) come from today's
    capacity_checkins row via capacity_zone_from_checkin(), not from this
    function's captains_log_entries read -- see _get_capacity_checkin_live()'s
    docstring. No today row means Unknown, never a stale prior day silently
    served as current (mission's explicit "absence must not imply Green"
    and "must not treat an old state as indefinitely current" requirements).
    """
    # compute_capacity_score (3rd return) is unused here since Mission 2's
    # fix below -- kept import for is_configured()/supabase_get, which are
    # still needed for the captains_log_entries narrative-field read.
    supabase_get, is_configured, _compute_cap_unused = _get_captains_log_live()

    if supabase_get and is_configured and is_configured():
        try:
            today = datetime.now().astimezone().date().isoformat()
            rows = supabase_get(
                f"captains_log_entries?log_date=eq.{today}&limit=1"
            )
            entry = rows[0] if rows else None

            # If no today entry, try latest
            if not entry:
                rows = supabase_get(
                    "captains_log_entries?order=log_date.desc&limit=1"
                )
                entry = rows[0] if rows else None

            # Get 7-day trends for pain and energy using canonical trend_utils (WP-4)
            trend_direction: str | None = None
            energy_trend_direction: str | None = None
            try:
                from datetime import timedelta
                _HEALTH_ROOT = Path(__file__).resolve().parents[2] / "core" / "health"
                if str(_HEALTH_ROOT) not in sys.path:
                    sys.path.insert(0, str(_HEALTH_ROOT))
                from trend_utils import (
                    compute_energy_trend,
                    compute_pain_trend,
                    encode_energy,
                )
                since = (datetime.now().astimezone().date() - timedelta(days=6)).isoformat()
                recent = supabase_get(
                    f"captains_log_entries?log_date=gte.{since}&order=log_date.asc&limit=7"
                )
                pain_vals = [float(r["pain_score"]) for r in recent if r.get("pain_score") is not None]
                result = compute_pain_trend(pain_vals)
                trend_direction = None if result == "insufficient_data" else result
                energy_vals = [encode_energy(r["energy"]) for r in recent if r.get("energy")]
                result_e = compute_energy_trend(energy_vals)
                energy_trend_direction = None if result_e == "insufficient_data" else result_e
            except Exception:  # noqa: BLE001,S110 - best-effort trend computation; None trend direction is a valid 'insufficient data' outcome
                pass

            # Capacity score/status: canonical capacity_checkins source
            # (Mission 2, USS-TJR-MSN-2), not captains_log_entries -- see
            # _get_capacity_checkin_live()'s docstring. `entry`/`compute_cap`
            # (captains_log_entries/compute_capacity_score) are no longer
            # used for capacity; kept only for this function's other
            # (non-capacity) narrative fields below.
            cap_score: int | None = None
            checkin_get, checkin_configured, zone_from_checkin = _get_capacity_checkin_live()
            if checkin_get and checkin_configured and checkin_configured():
                try:
                    checkin_today = datetime.now().astimezone().date().isoformat()
                    checkin_rows = checkin_get(
                        "capacity_checkins?log_date=eq."
                        f"{checkin_today}&checkin_type=eq.capacity&order=captured_at.desc&limit=1"
                    )
                    checkin_row = checkin_rows[0] if checkin_rows else None
                    cap_score, _ = zone_from_checkin(checkin_row)
                except Exception:  # noqa: BLE001 - no today capacity_checkins row/unreachable -> cap_score stays None (Unknown), never a stale fallback
                    cap_score = None

            return build_health_context_from_captains_log(
                entry, trend_direction, cap_score, assembled_at,
                energy_trend=energy_trend_direction,
            )
        except Exception:  # noqa: BLE001,S110 - already documented: fall through to the legacy Health-Summary.md path
            pass  # fall through to legacy path

    # Legacy fallback: read Health-Summary.md
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    health_path = _REPO_ROOT / "memory" / "Health-Summary.md"
    summary = parse_health_summary(health_path)
    return build_health_context(summary, assembled_at)
