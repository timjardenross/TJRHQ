#!/usr/bin/env python3
"""Governance-backed specialist routing for USS TJR retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "core/crew/registry/specialist-retrieval-registry.txt"
ROUTING_RULES_PATH = ROOT / "core/crew/registry/retrieval-routing-rules.txt"
OUTPUT_FORMAT_DIR = ROOT / "core/crew/output-formats"


OUTPUT_FORMAT_FILES = {
    "Chief Engineer": "chief-engineer-output-format.txt",
    "Chief of Staff": "chief-of-staff-output-format.txt",
    "Code Review Specialist": "code-review-specialist-output-format.txt",
    "Knowledge Manager": "knowledge-manager-output-format.txt",
    # MSN-0312: "Design Officer" (canonical) and "UX Design Officer" (legacy alias)
    # are the same specialist retitled; both map to the same output format file.
    "Design Officer": "ux-design-officer-output-format.txt",
    "UX Design Officer": "ux-design-officer-output-format.txt",
}

HIGH_SIGNAL_TERMS = {"code", "testing", "review", "quality", "defects"}


@dataclass(frozen=True)
class SpecialistProfile:
    name: str
    domains: list[str]
    allowed_types: list[str]
    output_sections: list[str]


@dataclass(frozen=True)
class RouteDecision:
    specialist: SpecialistProfile
    matched_terms: list[str]
    confidence: int
    escalation: str | None


def _split_values(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _section_titles(text: str) -> list[str]:
    sections = []
    for line in text.splitlines():
        match = re.match(r"^\d+\.\s+(.+)$", line.strip())
        if match:
            sections.append(match.group(1).strip())
    return sections


def load_specialist_profiles() -> dict[str, SpecialistProfile]:
    text = REGISTRY_PATH.read_text(encoding="utf-8")
    profiles: dict[str, SpecialistProfile] = {}
    current: str | None = None
    domains: list[str] = []
    allowed: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("File:") or line.startswith("Purpose:") or line.startswith("Dependencies/Notes:"):
            continue
        if not line.startswith(("Domains:", "Allowed Types:")):
            if current:
                profiles[current] = _profile(current, domains, allowed)
            current = line
            domains = []
            allowed = []
        elif line.startswith("Domains:"):
            domains = _split_values(line.split(":", 1)[1])
        elif line.startswith("Allowed Types:"):
            allowed = _split_values(line.split(":", 1)[1])
    if current:
        profiles[current] = _profile(current, domains, allowed)
    return profiles


def _profile(name: str, domains: list[str], allowed: list[str]) -> SpecialistProfile:
    format_file = OUTPUT_FORMAT_FILES.get(name, "specialist-output-format-standard.txt")
    output_path = OUTPUT_FORMAT_DIR / format_file
    if not output_path.exists():
        output_path = OUTPUT_FORMAT_DIR / "specialist-output-format-standard.txt"
    return SpecialistProfile(
        name=name,
        domains=domains,
        allowed_types=allowed,
        output_sections=_section_titles(output_path.read_text(encoding="utf-8")),
    )


def load_routing_rules() -> list[tuple[list[str], str]]:
    rules = []
    for raw_line in ROUTING_RULES_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or "->" not in line:
            continue
        left, right = line.split("->", 1)
        rules.append((_split_values(left), right.strip()))
    return rules


def route_question(question: str) -> RouteDecision:
    profiles = load_specialist_profiles()
    normalized = question.lower()
    best_role = "Knowledge Manager"
    best_terms: list[str] = []
    best_score = 0
    for terms, role in load_routing_rules():
        matched = [term for term in terms if term.lower() in normalized]
        score = sum(2 if term.lower() in HIGH_SIGNAL_TERMS else 1 for term in matched)
        if score > best_score:
            best_role = role
            best_terms = matched
            best_score = score
    if best_terms:
        confidence = min(95, 70 + (len(best_terms) * 10))
    else:
        confidence = 55
    escalation = None if confidence >= 70 else "Chief of Staff"
    return RouteDecision(
        specialist=profiles[best_role],
        matched_terms=best_terms,
        confidence=confidence,
        escalation=escalation,
    )
