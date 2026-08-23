"""
Knowledge Utilisation Intelligence — WP6
Mission: M-20260613-INTELLIGENCE-MATURITY-PHASE2

Analyses how lessons, ADRs, capabilities, decisions, and missions are referenced
and reused across the knowledge base.

Produces:
- Most referenced lessons
- Most referenced ADRs
- Most reused capabilities
- Unused knowledge assets
- Emerging knowledge clusters

Sources (all read-only):
- logs/decisions/*.json          (lesson_id references)
- knowledge/Lessons-Learned.md   (lesson inventory)
- core/governance/architecture-decision-records/*.md (ADR inventory)
- knowledge/ all markdown         (cross-references)
- capability-inventory.md         (capability inventory)

Public API:
    compute_knowledge_utilisation() -> dict
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Docling is the preferred extraction path; graceful fallback to read_text if unavailable.
try:
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from core.knowledge.docling_processor import extract_document as _docling_extract
except Exception:
    _docling_extract = None  # type: ignore[assignment]

# Source directories
_DECISIONS_DIR   = _REPO_ROOT / "logs" / "decisions"
_LESSONS_MD      = _REPO_ROOT / "knowledge" / "Lessons-Learned.md"
_KNOWLEDGE_DIR   = _REPO_ROOT / "knowledge"
_ADR_DIRS        = [
    _REPO_ROOT / "core" / "governance" / "architecture-decision-records",
    _REPO_ROOT / "governance" / "architecture-decision-records",
]
_CAPABILITY_FILE = _REPO_ROOT / "capability-inventory.md"


# ---------------------------------------------------------------------------
# ID patterns
# ---------------------------------------------------------------------------

_LL_PATTERN  = re.compile(r'\bLL-\d+\b')
_ADR_PATTERN = re.compile(r'\bADR-[\w\d-]+\b', re.IGNORECASE)
_CAP_PATTERN = re.compile(r'\bCAP-\d+\b', re.IGNORECASE)
_MSN_PATTERN = re.compile(r'\bMSN-[\w\d-]+\b', re.IGNORECASE)
_DEC_PATTERN = re.compile(r'\bDEC-[\d-]+\b', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Inventory loaders
# ---------------------------------------------------------------------------

def _load_lessons_inventory() -> dict[str, dict[str, str]]:
    """Returns {lesson_id: {title, mission_id}} from Lessons-Learned.md."""
    if not _LESSONS_MD.exists():
        return {}
    text = _LESSONS_MD.read_text(encoding="utf-8", errors="replace")
    lessons = {}
    for block in re.split(r'\n(?=## LL-)', text):
        id_m = re.match(r'## (LL-\d+)', block)
        if not id_m:
            continue
        lid = id_m.group(1)
        title_m = re.search(r'### Title\s*\n+(.+)', block)
        title = title_m.group(1).strip() if title_m else lid
        msn_m = re.search(r'### Mission\s*\n+(.+)', block)
        mission = msn_m.group(1).strip() if msn_m else None
        lessons[lid] = {"title": title, "mission_id": mission}
    return lessons


def _load_adr_inventory() -> dict[str, str]:
    """Returns {adr_id: title}."""
    adrs = {}
    for adr_dir in _ADR_DIRS:
        if not adr_dir.exists():
            continue
        for f in adr_dir.glob("ADR-*.md"):
            text = f.read_text(encoding="utf-8", errors="replace")
            title_m = re.search(r'^#\s+(.+)', text, re.MULTILINE)
            title = title_m.group(1).strip() if title_m else f.stem
            adr_id_m = re.search(r'\bADR-[\w\d-]+\b', f.stem, re.IGNORECASE)
            adr_id = adr_id_m.group(0).upper() if adr_id_m else f.stem.upper()
            adrs[adr_id] = title
    return adrs


def _load_capability_inventory() -> dict[str, str]:
    """Returns {cap_id: name} from capability-inventory.md."""
    caps = {}
    if not _CAPABILITY_FILE.exists():
        # Try searching knowledge dir
        for candidate in _KNOWLEDGE_DIR.rglob("*capability*inventory*"):
            if candidate.suffix == ".md":
                _CAPABILITY_FILE.resolve()  # no-op; just use candidate below
                text = candidate.read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r'\*\*(CAP-\d+)\*\*[:\s]+([^\n]+)', text, re.IGNORECASE):
                    caps[m.group(1).upper()] = m.group(2).strip()
                return caps
        return caps
    text = _CAPABILITY_FILE.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r'\*\*(CAP-\d+)\*\*[:\s]+([^\n]+)', text, re.IGNORECASE):
        caps[m.group(1).upper()] = m.group(2).strip()
    if not caps:
        # Fallback: ### blocks with CAP- IDs
        for block in re.split(r'\n(?=###)', text):
            id_m = re.search(r'(CAP-\d+)', block, re.IGNORECASE)
            name_m = re.match(r'###\s+(.+)', block)
            if id_m and name_m:
                caps[id_m.group(1).upper()] = name_m.group(1).strip()
    return caps


# ---------------------------------------------------------------------------
# Reference scanning
# ---------------------------------------------------------------------------

def _scan_decision_logs() -> dict[str, Any]:
    """Scan decision JSON logs for lesson_id, ADR, and mission references."""
    lesson_refs: Counter = Counter()
    adr_refs:    Counter = Counter()
    msn_refs:    Counter = Counter()

    for f in _DECISIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue

        # lesson_id field
        lid = data.get("lesson_id")
        if lid and isinstance(lid, str) and lid.startswith("LL-"):
            lesson_refs[lid] += 1

        # lesson_ids_generated field (list)
        for lid2 in (data.get("lesson_ids_generated") or []):
            if isinstance(lid2, str) and lid2.startswith("LL-"):
                lesson_refs[lid2] += 1

        # Full-text scan of all string values
        full_text = json.dumps(data)
        for m in _LL_PATTERN.findall(full_text):
            lesson_refs[m] += 1
        for m in _ADR_PATTERN.findall(full_text):
            adr_refs[m.upper()] += 1
        for m in _MSN_PATTERN.findall(full_text):
            msn_refs[m.upper()] += 1

    # Deduplicate (one file shouldn't count the same ID multiple times from text)
    # We accept double-counting from field + text scan as a soft signal
    return {
        "lesson_refs":  lesson_refs,
        "adr_refs":     adr_refs,
        "mission_refs": msn_refs,
    }


def _scan_knowledge_documents() -> dict[str, Any]:
    """Scan all markdown documents in knowledge/ for cross-references."""
    lesson_refs: Counter = Counter()
    adr_refs:    Counter = Counter()
    cap_refs:    Counter = Counter()
    msn_refs:    Counter = Counter()
    dec_refs:    Counter = Counter()

    for f in _KNOWLEDGE_DIR.rglob("*.md"):
        try:
            # Prefer Docling for structured extraction; fall back to raw read.
            _extracted = _docling_extract(f) if _docling_extract is not None else None
            if _extracted is not None:
                text = _extracted["text"]
            else:
                text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in _LL_PATTERN.findall(text):
            lesson_refs[m] += 1
        for m in _ADR_PATTERN.findall(text):
            adr_refs[m.upper()] += 1
        for m in _CAP_PATTERN.findall(text):
            cap_refs[m.upper()] += 1
        for m in _MSN_PATTERN.findall(text):
            msn_refs[m.upper()] += 1
        for m in _DEC_PATTERN.findall(text):
            dec_refs[m.upper()] += 1

    return {
        "lesson_refs":     lesson_refs,
        "adr_refs":        adr_refs,
        "capability_refs": cap_refs,
        "mission_refs":    msn_refs,
        "decision_refs":   dec_refs,
    }


# ---------------------------------------------------------------------------
# Cluster detection
# ---------------------------------------------------------------------------

def _detect_clusters(
    lesson_refs: Counter,
    adr_refs:    Counter,
    cap_refs:    Counter,
) -> list[str]:
    """Identify emerging knowledge clusters (co-referenced asset groups)."""
    clusters = []
    if lesson_refs and any(c >= 3 for c in lesson_refs.values()):
        top = [k for k, v in lesson_refs.most_common(3)]
        clusters.append(f"High-reuse lessons: {', '.join(top)}")
    if adr_refs and any(c >= 2 for c in adr_refs.values()):
        top = [k for k, v in adr_refs.most_common(2)]
        clusters.append(f"Frequently referenced ADRs: {', '.join(top)}")
    if cap_refs and any(c >= 2 for c in cap_refs.values()):
        top = [k for k, v in cap_refs.most_common(2)]
        clusters.append(f"Most reused capabilities: {', '.join(top)}")
    return clusters


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_knowledge_utilisation() -> dict[str, Any]:
    """
    Compute knowledge utilisation metrics across all reference sources.

    Returns structured report with most/least referenced assets and clusters.
    """
    lessons_inv = _load_lessons_inventory()
    adr_inv     = _load_adr_inventory()
    cap_inv     = _load_capability_inventory()

    decision_refs = _scan_decision_logs()
    doc_refs      = _scan_knowledge_documents()

    # Merge lesson refs from both sources
    lesson_total: Counter = Counter()
    lesson_total.update(decision_refs["lesson_refs"])
    lesson_total.update(doc_refs["lesson_refs"])

    adr_total: Counter = Counter()
    adr_total.update(decision_refs["adr_refs"])
    adr_total.update(doc_refs["adr_refs"])

    cap_total: Counter = doc_refs["capability_refs"]
    msn_total: Counter = Counter()
    msn_total.update(decision_refs["mission_refs"])
    msn_total.update(doc_refs["mission_refs"])

    dec_total: Counter = doc_refs["decision_refs"]

    # ── Most referenced ──────────────────────────────────────────────────────
    def _ranked(counter: Counter, inventory: dict, n: int = 5) -> list[dict]:
        result = []
        for asset_id, count in counter.most_common(n):
            meta = inventory.get(asset_id, inventory.get(asset_id.upper(), {}))
            if isinstance(meta, str):
                meta = {"title": meta}
            result.append({
                "id": asset_id,
                "title": meta.get("title", asset_id) if isinstance(meta, dict) else asset_id,
                "reference_count": count,
            })
        return result

    most_ref_lessons = _ranked(lesson_total, lessons_inv)
    most_ref_adrs    = _ranked(adr_total,    adr_inv)
    most_ref_caps    = _ranked(cap_total,    cap_inv)

    # ── Unused assets ────────────────────────────────────────────────────────
    unused_lessons = [
        {"id": lid, "title": meta["title"]}
        for lid, meta in lessons_inv.items()
        if lesson_total.get(lid, 0) == 0
    ]
    unused_adrs = [
        {"id": aid, "title": title}
        for aid, title in adr_inv.items()
        if adr_total.get(aid, 0) == 0
    ]
    unused_caps = [
        {"id": cid, "name": name}
        for cid, name in cap_inv.items()
        if cap_total.get(cid, 0) == 0
    ]

    # ── Clusters ─────────────────────────────────────────────────────────────
    clusters = _detect_clusters(lesson_total, adr_total, cap_total)

    # ── Summary ──────────────────────────────────────────────────────────────
    findings = _build_findings(
        lessons_inv, adr_inv, cap_inv,
        most_ref_lessons, most_ref_adrs, most_ref_caps,
        unused_lessons, unused_adrs, unused_caps,
        clusters,
    )

    return {
        "status": "ok",
        "inventory": {
            "total_lessons": len(lessons_inv),
            "total_adrs":    len(adr_inv),
            "total_caps":    len(cap_inv),
        },
        "reference_counts": {
            "lessons":     dict(lesson_total.most_common()),
            "adrs":        dict(adr_total.most_common()),
            "capabilities": dict(cap_total.most_common()),
            "missions":    dict(msn_total.most_common(10)),
            "decisions":   dict(dec_total.most_common(10)),
        },
        "most_referenced_lessons": most_ref_lessons,
        "most_referenced_adrs":    most_ref_adrs,
        "most_reused_capabilities": most_ref_caps,
        "unused_lessons":  unused_lessons,
        "unused_adrs":     unused_adrs,
        "unused_capabilities": unused_caps,
        "emerging_clusters": clusters,
        "findings": findings,
    }


def _build_findings(
    lessons_inv, adr_inv, cap_inv,
    most_ref_lessons, most_ref_adrs, most_ref_caps,
    unused_lessons, unused_adrs, unused_caps,
    clusters,
) -> list[str]:
    findings = []

    if most_ref_lessons:
        top = most_ref_lessons[0]
        findings.append(
            f"MOST VALUABLE LESSON: {top['id']} \"{top['title']}\" "
            f"({top['reference_count']} references)"
        )

    if most_ref_adrs:
        top = most_ref_adrs[0]
        findings.append(
            f"MOST INFLUENTIAL ADR: {top['id']} \"{top['title']}\" "
            f"({top['reference_count']} references)"
        )

    if most_ref_caps:
        top = most_ref_caps[0]
        findings.append(
            f"MOST REUSED CAPABILITY: {top['id']} \"{top['title']}\" "
            f"({top['reference_count']} references)"
        )

    if unused_lessons:
        ids = ", ".join(l["id"] for l in unused_lessons[:3])
        findings.append(
            f"UNUSED LESSONS ({len(unused_lessons)}): {ids}"
            + (" and more" if len(unused_lessons) > 3 else "")
        )

    if unused_adrs:
        ids = ", ".join(a["id"] for a in unused_adrs[:3])
        findings.append(f"UNREFERENCED ADRs ({len(unused_adrs)}): {ids}")

    for cluster in clusters:
        findings.append(f"CLUSTER: {cluster}")

    return findings
