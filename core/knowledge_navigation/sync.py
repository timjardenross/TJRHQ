"""
sync.py: Reads hierarchy source files and upserts knowledge_nodes + knowledge_edges
to Supabase (and rebuilds the in-memory graph).

Sources processed (in order):
  0. knowledge/Captains-Directives.md        → principle nodes (Level 0)
  1. knowledge/hierarchy/Objectives.md       → objective nodes + principle edges
  2. knowledge/hierarchy/Initiatives.md      → initiative nodes + edges to objectives, ADRs, missions
  3. governance/ADR-*.md                     → adr nodes + cross-ref edges
  4. knowledge/Lessons-Learned.md            → lesson nodes + mission/decision edges
  5. knowledge/decisions/*.md                → decision nodes
  6. Missions/Active/*.md                    → mission nodes + adr/decision edges
  7. knowledge/hierarchy/overrides.yaml      → manual edge overrides

Usage:
  python3 -m core.knowledge_navigation.sync
  python3 -m core.knowledge_navigation.sync --dry-run
  python3 -m core.knowledge_navigation.sync --source objectives
  python3 -m core.knowledge_navigation.sync --source principles
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.knowledge_navigation.models import (  # noqa: E402
    HierarchyEdge,
    HierarchyNode,
    NODE_LEVELS,
    VALID_RELATIONSHIP_TYPES,
)
from core.knowledge_navigation.index import get_index, reload_graph  # noqa: E402

# ---------------------------------------------------------------------------
# ID normalisation patterns
# ---------------------------------------------------------------------------

_RE_OBJ = re.compile(r"\bOBJ-(\d+)\b", re.IGNORECASE)
_RE_INI = re.compile(r"\bINI-(\d+)\b", re.IGNORECASE)
_RE_MSN = re.compile(r"\b(?:USS-TJR-)?MSN-(\d{4}[A-Z]?)\b", re.IGNORECASE)
_RE_ADR = re.compile(r"\bADR-(\d{1,3})\b", re.IGNORECASE)
_RE_LL  = re.compile(r"\bLL-(\d{1,3})\b", re.IGNORECASE)
_RE_DEC = re.compile(r"\bDEC-(\d{8}-[\d]+)\b", re.IGNORECASE)
_RE_CD  = re.compile(r"\bCD-(\d{3})\b", re.IGNORECASE)

# Keyword → relationship type (for body-text extraction)
_KEYWORD_RELS = [
    (re.compile(r"governed[_ ]by\s*:", re.I),   "governed_by",  0.90),
    (re.compile(r"triggered[_ ]by\s*:", re.I),  "produces",     0.85),
    (re.compile(r"depends[_ ]on\s*:", re.I),    "depends_on",   0.85),
    (re.compile(r"supersedes\s*:", re.I),        "supersedes",   0.90),
    (re.compile(r"governed by|aligns with adr",  re.I), "governed_by", 0.70),
    (re.compile(r"depends on|requires|blocked by", re.I), "depends_on", 0.65),
]


def _norm_msn(digits: str) -> str:
    # MSN IDs are 4 digits, optional letter suffix
    m = re.match(r"(\d+)([A-Z]?)", digits.upper())
    if not m:
        return f"MSN-{digits.upper()}"
    num = m.group(1).zfill(4)
    return f"MSN-{num}{m.group(2)}"


def _norm_adr(digits: str) -> str:
    return f"ADR-{digits.zfill(3)}"


def _norm_ll(digits: str) -> str:
    return f"LL-{digits.zfill(3)}"


def _norm_obj(digits: str) -> str:
    return f"OBJ-{digits.zfill(3)}"


def _norm_ini(digits: str) -> str:
    return f"INI-{digits.zfill(3)}"


def _norm_cd(digits: str) -> str:
    return f"CD-{digits.zfill(3)}"


# ---------------------------------------------------------------------------
# Markdown table parser (| **Field** | Value | rows)
# ---------------------------------------------------------------------------

def _parse_md_table(text: str) -> dict[str, str]:
    """Extract key→value pairs from a markdown table block."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 2:
            continue
        key = re.sub(r"\*+", "", parts[0]).strip().lower().replace(" ", "_")
        val = parts[1].strip()
        if key and val:
            result[key] = val
    return result


# ---------------------------------------------------------------------------
# Source parsers
# ---------------------------------------------------------------------------

def _parse_principles(path: Path) -> tuple[list[HierarchyNode], list[HierarchyEdge]]:
    """Parse knowledge/Captains-Directives.md → principle nodes (Level 0)."""
    if not path.exists():
        log.info("[sync] Captains-Directives.md not found at %s — skipping", path)
        return [], []

    text = path.read_text(encoding="utf-8")
    nodes: list[HierarchyNode] = []

    # Each directive is a ## Directive NNN — Title section
    sections = re.split(r"(?=^## Directive )", text, flags=re.MULTILINE)
    for section in sections:
        m = re.match(r"^## Directive (\d+)\s*[—–-]\s*(.+)", section.strip(), re.IGNORECASE)
        if not m:
            continue
        num = m.group(1).zfill(3)
        node_id = f"CD-{num}"
        title = m.group(2).strip()

        # Status from STATUS: line (CD-055 pattern) or assume active
        status_m = re.search(r"^STATUS:\s*(.+)", section, re.MULTILINE | re.IGNORECASE)
        raw_status = status_m.group(1).strip().lower() if status_m else "approved"
        status = "active" if raw_status in ("approved", "active") else raw_status

        # Metadata: effective_date, category if present
        meta: dict = {"directive_number": num, "owner": "Captain TJR"}
        eff_m = re.search(r"^EFFECTIVE DATE:\s*(.+)", section, re.MULTILINE | re.IGNORECASE)
        cat_m = re.search(r"^CATEGORY:\s*(.+)", section, re.MULTILINE | re.IGNORECASE)
        if eff_m:
            meta["effective_date"] = eff_m.group(1).strip()
        if cat_m:
            meta["category"] = cat_m.group(1).strip()

        summary = _extract_prose(section)

        nodes.append(HierarchyNode(
            node_id=node_id,
            node_type="principle",
            level=NODE_LEVELS["principle"],
            title=title,
            summary=summary[:500],
            status=status,
            source_file=str(path.relative_to(_REPO_ROOT)),
            metadata=meta,
        ))

    log.info("[sync] principles: %d nodes", len(nodes))
    return nodes, []  # edges come from overrides.yaml directive_objectives section


def _parse_objectives(path: Path) -> tuple[list[HierarchyNode], list[HierarchyEdge]]:
    """Parse knowledge/hierarchy/Objectives.md → objective nodes + principle edges."""
    if not path.exists():
        log.info("[sync] Objectives.md not found at %s — skipping", path)
        return [], []

    text = path.read_text(encoding="utf-8")
    nodes: list[HierarchyNode] = []
    edges: list[HierarchyEdge] = []

    # Split into sections by ### OBJ-NNN heading
    sections = re.split(r"(?=^### OBJ-)", text, flags=re.MULTILINE)
    for section in sections:
        m = re.match(r"^### (OBJ-\d+)\s*[—–-]\s*(.+)", section.strip(), re.IGNORECASE)
        if not m:
            continue
        node_id = _norm_obj(m.group(1).split("-", 1)[1])
        title = m.group(2).strip()

        fields = _parse_md_table(section)
        status = fields.get("status", "active").lower()
        derives_from = fields.get("derives_from", "")
        stage = fields.get("stage", "")
        horizon = fields.get("horizon", "")

        # Summary: first non-table, non-heading prose paragraph
        summary = _extract_prose(section)

        nodes.append(HierarchyNode(
            node_id=node_id,
            node_type="objective",
            level=NODE_LEVELS["objective"],
            title=title,
            summary=summary,
            status=status,
            source_file=str(path.relative_to(_REPO_ROOT)),
            metadata={"stage": stage, "horizon": horizon},
        ))

        # Edges to Captain's Directives (CD-XXX)
        for cd_match in _RE_CD.finditer(derives_from):
            cd_id = _norm_cd(cd_match.group(1))
            edges.append(HierarchyEdge(
                source_id=cd_id,
                target_id=node_id,
                relationship_type="expresses",
                confidence=1.0,
                evidence=f"Derives From: {derives_from}",
            ))

    log.info("[sync] objectives: %d nodes, %d edges", len(nodes), len(edges))
    return nodes, edges


def _parse_initiatives(path: Path) -> tuple[list[HierarchyNode], list[HierarchyEdge]]:
    """Parse knowledge/hierarchy/Initiatives.md → initiative nodes + edges."""
    if not path.exists():
        log.info("[sync] Initiatives.md not found at %s — skipping", path)
        return [], []

    text = path.read_text(encoding="utf-8")
    nodes: list[HierarchyNode] = []
    edges: list[HierarchyEdge] = []

    sections = re.split(r"(?=^### INI-)", text, flags=re.MULTILINE)
    for section in sections:
        m = re.match(r"^### (INI-\d+)\s*[—–-]\s*(.+)", section.strip(), re.IGNORECASE)
        if not m:
            continue
        node_id = _norm_ini(m.group(1).split("-", 1)[1])
        title = m.group(2).strip()

        fields = _parse_md_table(section)
        status = fields.get("status", "active").lower()
        pursues = fields.get("pursues", "") or fields.get("objective", "")
        governed_by_raw = fields.get("governed_by", "")
        stage = fields.get("stage", "")

        summary = _extract_prose(section)

        nodes.append(HierarchyNode(
            node_id=node_id,
            node_type="initiative",
            level=NODE_LEVELS["initiative"],
            title=title,
            summary=summary,
            status=status,
            source_file=str(path.relative_to(_REPO_ROOT)),
            metadata={"stage": stage},
        ))

        # Edge: initiative pursues objective
        for obj_match in _RE_OBJ.finditer(pursues):
            obj_id = _norm_obj(obj_match.group(1))
            edges.append(HierarchyEdge(
                source_id=node_id,
                target_id=obj_id,
                relationship_type="pursues",
                confidence=1.0,
                evidence=f"Pursues: {pursues}",
            ))

        # Edges: initiative governed_by ADRs
        for adr_match in _RE_ADR.finditer(governed_by_raw):
            adr_id = _norm_adr(adr_match.group(1))
            edges.append(HierarchyEdge(
                source_id=node_id,
                target_id=adr_id,
                relationship_type="governed_by",
                confidence=1.0,
                evidence=f"Governed By: {governed_by_raw}",
            ))

        # Edges: initiative contains missions (from **Missions:** list)
        missions_block = _extract_missions_block(section)
        for msn_match in _RE_MSN.finditer(missions_block):
            msn_id = _norm_msn(msn_match.group(1))
            edges.append(HierarchyEdge(
                source_id=node_id,
                target_id=msn_id,
                relationship_type="contains",
                confidence=1.0,
                evidence=f"Missions list in {node_id}",
            ))

    log.info("[sync] initiatives: %d nodes, %d edges", len(nodes), len(edges))
    return nodes, edges


def _parse_adrs(governance_dir: Path) -> tuple[list[HierarchyNode], list[HierarchyEdge]]:
    """Parse governance/ADR-*.md → adr nodes + cross-ref edges."""
    nodes: list[HierarchyNode] = []
    edges: list[HierarchyEdge] = []

    for adr_file in sorted(governance_dir.glob("ADR-*.md")):
        text = adr_file.read_text(encoding="utf-8")

        # Extract ID from H1: # ADR-009 — Title
        h1 = re.search(r"^#\s+(ADR-\d+)\s*[—–-]\s*(.+)", text, re.MULTILINE)
        if not h1:
            continue
        node_id = _norm_adr(h1.group(1).split("-", 1)[1])
        title = h1.group(2).strip()

        fields = _parse_md_table(text)
        status = fields.get("status", "active").upper()
        # Normalise: ACCEPTED → active, DEPRECATED → archived
        status_map = {"ACCEPTED": "active", "PROPOSED": "draft", "DEPRECATED": "archived",
                      "SUPERSEDED": "archived", "REJECTED": "archived"}
        status = status_map.get(status, status.lower())

        # Summary: first substantial paragraph after the table
        summary = _extract_prose(text)

        nodes.append(HierarchyNode(
            node_id=node_id,
            node_type="adr",
            level=NODE_LEVELS["adr"],
            title=title,
            summary=summary[:500],
            status=status,
            source_file=str(adr_file.relative_to(_REPO_ROOT)),
        ))

        # Extract Supersedes edges
        supersedes_val = fields.get("supersedes", "")
        for adr_match in _RE_ADR.finditer(supersedes_val):
            target_id = _norm_adr(adr_match.group(1))
            edges.append(HierarchyEdge(
                source_id=node_id,
                target_id=target_id,
                relationship_type="supersedes",
                confidence=1.0,
                evidence=f"Supersedes: {supersedes_val}",
            ))

        # Extract body-text ADR → ADR references (informs, governed_by patterns)
        _extract_body_edges(node_id, text, edges, sources={"adr"})

    log.info("[sync] ADRs: %d nodes, %d edges", len(nodes), len(edges))
    return nodes, edges


def _parse_lessons(path: Path) -> tuple[list[HierarchyNode], list[HierarchyEdge]]:
    """Parse knowledge/Lessons-Learned.md → lesson nodes + edges to missions/decisions."""
    if not path.exists():
        return [], []

    text = path.read_text(encoding="utf-8")
    nodes: list[HierarchyNode] = []
    edges: list[HierarchyEdge] = []

    sections = re.split(r"(?=^### LL-)", text, flags=re.MULTILINE)
    for section in sections:
        m = re.match(r"^### (LL-\d+)\s*[—–-]\s*(.+)", section.strip(), re.IGNORECASE)
        if not m:
            continue
        node_id = _norm_ll(m.group(1).split("-", 1)[1])
        title = m.group(2).strip()

        # Inline fields: **Type:** x | **Recurrence:** y | **Strategic Value:** z | **Confidence:** w
        inline = re.search(
            r"\*\*Type:\*\*\s*([^|]+?)\s*\|.*?\*\*Confidence:\*\*\s*([\d.]+)",
            section, re.IGNORECASE
        )
        confidence = 1.0
        if inline:
            try:
                confidence = float(inline.group(2).strip())
            except ValueError:
                pass

        summary = _extract_prose(section)

        nodes.append(HierarchyNode(
            node_id=node_id,
            node_type="lesson",
            level=NODE_LEVELS["lesson"],
            title=title,
            summary=summary[:400],
            status="active",
            source_file=str(path.relative_to(_REPO_ROOT)),
            metadata={"confidence": confidence},
        ))

        # Edges from Sources: field → missions, decisions, adrs
        sources_m = re.search(r"\*\*Sources?:\*\*\s*(.+)", section, re.IGNORECASE)
        if sources_m:
            sources_text = sources_m.group(1)
            for msn_m in _RE_MSN.finditer(sources_text):
                msn_id = _norm_msn(msn_m.group(1))
                edges.append(HierarchyEdge(
                    source_id=msn_id,
                    target_id=node_id,
                    relationship_type="generates",
                    confidence=0.85,
                    evidence=f"Source reference in {node_id}",
                ))
            for adr_m in _RE_ADR.finditer(sources_text):
                adr_id = _norm_adr(adr_m.group(1))
                edges.append(HierarchyEdge(
                    source_id=adr_id,
                    target_id=node_id,
                    relationship_type="generates",
                    confidence=0.80,
                    evidence=f"ADR source reference in {node_id}",
                ))

    log.info("[sync] lessons: %d nodes, %d edges", len(nodes), len(edges))
    return nodes, edges


def _parse_decisions(decisions_dir: Path) -> tuple[list[HierarchyNode], list[HierarchyEdge]]:
    """Parse knowledge/decisions/*.md → decision nodes."""
    nodes: list[HierarchyNode] = []
    edges: list[HierarchyEdge] = []

    for dec_file in sorted(decisions_dir.glob("*.md")):
        text = dec_file.read_text(encoding="utf-8")
        # Decision ID from filename or H1
        h1 = re.search(r"^#\s+(DEC-[\d-]+|Decision[:\s].+)", text, re.MULTILINE | re.IGNORECASE)
        dec_id_m = _RE_DEC.search(dec_file.stem) or (h1 and _RE_DEC.search(h1.group(0)))
        if not dec_id_m:
            continue
        node_id = f"DEC-{dec_id_m.group(1).upper()}"
        title = h1.group(1).strip() if h1 else dec_file.stem

        nodes.append(HierarchyNode(
            node_id=node_id,
            node_type="decision",
            level=NODE_LEVELS["decision"],
            title=title[:200],
            summary=_extract_prose(text)[:400],
            status="active",
            source_file=str(dec_file.relative_to(_REPO_ROOT)),
        ))

        _extract_body_edges(node_id, text, edges, sources={"adr", "mission"})

    log.info("[sync] decisions: %d nodes, %d edges", len(nodes), len(edges))
    return nodes, edges


def _parse_active_missions(missions_dir: Path) -> tuple[list[HierarchyNode], list[HierarchyEdge]]:
    """Parse Missions/Active/*.md → mission nodes + adr/decision edges."""
    nodes: list[HierarchyNode] = []
    edges: list[HierarchyEdge] = []

    for msn_file in sorted(missions_dir.glob("*.md")):
        text = msn_file.read_text(encoding="utf-8")

        # MSN ID from filename
        msn_m = _RE_MSN.search(msn_file.stem)
        if not msn_m:
            continue
        node_id = _norm_msn(msn_m.group(1))

        # Title from H1
        h1 = re.search(r"^#\s+(?:USS-TJR-)?MSN-\S+\s*[—–-]\s*(.+)", text, re.MULTILINE)
        title = h1.group(1).strip() if h1 else msn_file.stem

        # Status from **Status:** field
        status_m = re.search(r"\*\*Status:\*\*\s*(.+)", text, re.IGNORECASE)
        raw_status = status_m.group(1).strip().split()[0].lower() if status_m else "active"
        # Map to standard values
        status_map = {
            "in_progress": "active", "active": "active", "planned": "planned",
            "blocked": "blocked", "completed": "completed", "deferred": "deferred",
            "cancelled": "archived", "archived": "archived",
        }
        status = status_map.get(raw_status, "active")

        # Initiative from **Initiative:** field (forward-only for new missions)
        ini_m = re.search(r"\*\*Initiative:\*\*\s*(INI-\d+)", text, re.IGNORECASE)

        nodes.append(HierarchyNode(
            node_id=node_id,
            node_type="mission",
            level=NODE_LEVELS["mission"],
            title=title[:200],
            summary=_extract_prose(text)[:400],
            status=status,
            source_file=str(msn_file.relative_to(_REPO_ROOT)),
        ))

        # If Initiative field present, create contains edge
        if ini_m:
            ini_id = _norm_ini(ini_m.group(1).split("-", 1)[1])
            edges.append(HierarchyEdge(
                source_id=ini_id,
                target_id=node_id,
                relationship_type="contains",
                confidence=1.0,
                evidence=f"Initiative field in {node_id}",
            ))

        # Body-text edge extraction
        _extract_body_edges(node_id, text, edges, sources={"adr", "decision"})

    log.info("[sync] active missions: %d nodes, %d edges", len(nodes), len(edges))
    return nodes, edges


def _parse_overrides(path: Path) -> list[HierarchyEdge]:
    """Parse knowledge/hierarchy/overrides.yaml → manual edge overrides."""
    if not path.exists():
        return []

    try:
        import yaml  # optional dependency
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        # Fallback: simple line parser for key: value pairs under section headers
        data = _parse_simple_yaml(path.read_text(encoding="utf-8"))

    edges: list[HierarchyEdge] = []

    def _add(source: str, target: str, rel: str) -> None:
        if source and target:
            edges.append(HierarchyEdge(
                source_id=source.upper(),
                target_id=target.upper(),
                relationship_type=rel,
                confidence=1.0,
                evidence="manual override",
            ))

    for msn_id, ini_id in (data.get("mission_initiatives") or {}).items():
        _add(ini_id, msn_id, "contains")

    for ll_id, dec_id in (data.get("lesson_decisions") or {}).items():
        _add(dec_id, ll_id, "informed_by")

    for adr_id, obj_id in (data.get("adr_objectives") or {}).items():
        _add(adr_id, obj_id, "governed_by")

    for cd_id, obj_id in (data.get("directive_objectives") or {}).items():
        _add(cd_id, obj_id, "expresses")

    for source_id, target_id in (data.get("custom_edges") or {}).items():
        parts = str(source_id).split("→", 1)
        if len(parts) == 2:
            _add(parts[0].strip(), parts[1].strip(), "references")

    log.info("[sync] overrides: %d manual edges", len(edges))
    return edges


def _parse_simple_yaml(text: str) -> dict:
    """Minimal YAML parser for the overrides file (no PyYAML required)."""
    result: dict = {}
    current_section: str | None = None
    for line in text.splitlines():
        stripped = line.rstrip()
        if not stripped or stripped.lstrip().startswith("#"):
            continue
        if not stripped.startswith(" ") and not stripped.startswith("\t"):
            if ":" in stripped:
                key = stripped.split(":", 1)[0].strip()
                val = stripped.split(":", 1)[1].strip()
                if not val or val == "{}":
                    current_section = key
                    result[key] = {}
                else:
                    current_section = None
        else:
            if current_section and ":" in stripped:
                k, _, v = stripped.strip().partition(":")
                result[current_section][k.strip()] = v.strip()
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_prose(text: str) -> str:
    """Return the first non-table, non-heading prose paragraph from text."""
    lines = text.splitlines()
    prose_lines: list[str] = []
    in_table = False
    found_heading = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if found_heading:
                break
            found_heading = True
            continue
        if stripped.startswith("|"):
            in_table = True
            continue
        if in_table and not stripped.startswith("|"):
            in_table = False
        if in_table:
            continue
        if stripped.startswith("**") and stripped.endswith(":**"):
            continue  # field label line
        if stripped:
            prose_lines.append(stripped)
        elif prose_lines:
            break  # end of first paragraph

    return " ".join(prose_lines)[:600]


def _extract_missions_block(section: str) -> str:
    """Extract the content of a **Missions:** block."""
    m = re.search(r"\*\*Missions?:\*\*\s*\n((?:\s*-\s+.+\n?)+)", section, re.IGNORECASE)
    return m.group(1) if m else ""


def _extract_body_edges(
    source_id: str,
    text: str,
    edges: list[HierarchyEdge],
    sources: set[str],
) -> None:
    """Extract ID references from body text, appending inferred edges."""
    if "adr" in sources:
        for m in _RE_ADR.finditer(text):
            target_id = _norm_adr(m.group(1))
            if target_id == source_id:
                continue
            ctx = text[max(0, m.start() - 80):m.end() + 80]
            rel, conf = _infer_rel(ctx, "governed_by", 0.65)
            edges.append(HierarchyEdge(
                source_id=source_id,
                target_id=target_id,
                relationship_type=rel,
                confidence=conf,
                evidence=ctx.replace("\n", " ").strip()[:200],
            ))
    if "decision" in sources:
        for m in _RE_DEC.finditer(text):
            target_id = f"DEC-{m.group(1).upper()}"
            if target_id == source_id:
                continue
            ctx = text[max(0, m.start() - 80):m.end() + 80]
            rel, conf = _infer_rel(ctx, "produces", 0.60)
            edges.append(HierarchyEdge(
                source_id=source_id,
                target_id=target_id,
                relationship_type=rel,
                confidence=conf,
                evidence=ctx.replace("\n", " ").strip()[:200],
            ))
    if "mission" in sources:
        for m in _RE_MSN.finditer(text):
            target_id = _norm_msn(m.group(1))
            if target_id == source_id:
                continue
            ctx = text[max(0, m.start() - 80):m.end() + 80]
            rel, conf = _infer_rel(ctx, "references", 0.55)
            edges.append(HierarchyEdge(
                source_id=source_id,
                target_id=target_id,
                relationship_type=rel,
                confidence=conf,
                evidence=ctx.replace("\n", " ").strip()[:200],
            ))


def _infer_rel(ctx: str, default_rel: str, default_conf: float) -> tuple[str, float]:
    for pattern, rel, boost in _KEYWORD_RELS:
        if pattern.search(ctx):
            return rel, min(1.0, default_conf + boost)
    return default_rel, default_conf


# ---------------------------------------------------------------------------
# Main sync runner
# ---------------------------------------------------------------------------

class SyncResult:
    def __init__(self) -> None:
        self.nodes_upserted = 0
        self.edges_upserted = 0
        self.errors: list[str] = []


def run_sync(
    *,
    dry_run: bool = False,
    source: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> SyncResult:
    root = repo_root or _REPO_ROOT
    result = SyncResult()

    all_nodes: list[HierarchyNode] = []
    all_edges: list[HierarchyEdge] = []

    sources_to_run = {source} if source else {
        "principles", "objectives", "initiatives", "adrs", "lessons",
        "decisions", "missions", "overrides",
    }

    # Known node IDs — used to filter edges so we don't reference phantom nodes
    # (edges to non-existent nodes would violate the FK constraint)
    # Build this set after collecting all nodes.

    if "principles" in sources_to_run:
        n, e = _parse_principles(root / "knowledge" / "Captains-Directives.md")
        all_nodes.extend(n)
        all_edges.extend(e)

    if "objectives" in sources_to_run:
        n, e = _parse_objectives(root / "knowledge" / "hierarchy" / "Objectives.md")
        all_nodes.extend(n)
        all_edges.extend(e)

    if "initiatives" in sources_to_run:
        n, e = _parse_initiatives(root / "knowledge" / "hierarchy" / "Initiatives.md")
        all_nodes.extend(n)
        all_edges.extend(e)

    if "adrs" in sources_to_run:
        n, e = _parse_adrs(root / "governance")
        all_nodes.extend(n)
        all_edges.extend(e)

    if "lessons" in sources_to_run:
        n, e = _parse_lessons(root / "knowledge" / "Lessons-Learned.md")
        all_nodes.extend(n)
        all_edges.extend(e)

    if "decisions" in sources_to_run:
        dec_dir = root / "knowledge" / "decisions"
        if dec_dir.exists():
            n, e = _parse_decisions(dec_dir)
            all_nodes.extend(n)
            all_edges.extend(e)

    if "missions" in sources_to_run:
        n, e = _parse_active_missions(root / "Missions" / "Active")
        all_nodes.extend(n)
        all_edges.extend(e)

    if "overrides" in sources_to_run:
        override_edges = _parse_overrides(root / "knowledge" / "hierarchy" / "overrides.yaml")
        all_edges.extend(override_edges)

    # Deduplicate nodes by node_id (last one wins — later sources are more specific)
    node_map: dict[str, HierarchyNode] = {}
    for n in all_nodes:
        node_map[n.node_id] = n
    unique_nodes = list(node_map.values())

    # Filter edges: both endpoints must be known nodes
    known_ids = set(node_map.keys())
    valid_edges = [
        e for e in all_edges
        if e.source_id in known_ids and e.target_id in known_ids
        and e.relationship_type in VALID_RELATIONSHIP_TYPES
    ]
    dropped = len(all_edges) - len(valid_edges)
    if dropped:
        log.info("[sync] Dropped %d edges referencing unknown nodes", dropped)

    log.info(
        "[sync] Prepared: %d nodes, %d edges (dry_run=%s)",
        len(unique_nodes), len(valid_edges), dry_run,
    )

    if dry_run:
        result.nodes_upserted = len(unique_nodes)
        result.edges_upserted = len(valid_edges)
        return result

    index = get_index()
    if not index.enabled:
        log.warning("[sync] Supabase not configured — in-memory graph updated only")
        # Still update the in-memory graph
        g = reload_graph()
        for n in unique_nodes:
            g.add_node(n)
        for e in valid_edges:
            g.add_edge(e)
        result.nodes_upserted = len(unique_nodes)
        result.edges_upserted = len(valid_edges)
        return result

    # Upsert nodes first (edges FK-reference nodes)
    ok_nodes = index.upsert_nodes(unique_nodes)
    if not ok_nodes:
        result.errors.append("node upsert failed")

    ok_edges = index.upsert_edges(valid_edges)
    if not ok_edges:
        result.errors.append("edge upsert failed")

    # Reload in-memory graph from Supabase
    reload_graph()

    result.nodes_upserted = len(unique_nodes)
    result.edges_upserted = len(valid_edges)
    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Sync knowledge hierarchy to Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no writes")
    parser.add_argument(
        "--source",
        choices=["principles", "objectives", "initiatives", "adrs", "lessons", "decisions", "missions", "overrides"],
        help="Sync only this source (default: all)",
    )
    args = parser.parse_args()

    result = run_sync(dry_run=args.dry_run, source=args.source)
    print(f"Sync complete: {result.nodes_upserted} nodes, {result.edges_upserted} edges")
    if result.errors:
        print(f"Errors: {', '.join(result.errors)}")
        sys.exit(1)
