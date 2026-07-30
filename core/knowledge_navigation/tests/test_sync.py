"""Tests for sync.py parsers -- file-based, no Supabase required."""
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import core.knowledge_navigation.sync as sync_module
from core.knowledge_navigation.sync import (
    _norm_msn,
    _norm_ini,
    _norm_obj,
    _norm_adr,
    _norm_ll,
    _parse_md_table,
    _extract_prose,
    _parse_objectives,
    _parse_initiatives,
    _parse_overrides,
)


# ── ID normalisers (accept digit-group capture from regex) ────────────────────

def test_norm_msn_plain():
    assert _norm_msn("0053") == "MSN-0053"

def test_norm_msn_short():
    assert _norm_msn("53") == "MSN-0053"

def test_norm_msn_with_letter():
    assert _norm_msn("0040A") == "MSN-0040A"

def test_norm_ini():
    assert _norm_ini("2") == "INI-002"

def test_norm_obj():
    assert _norm_obj("1") == "OBJ-001"

def test_norm_adr():
    assert _norm_adr("9") == "ADR-009"

def test_norm_ll():
    assert _norm_ll("3") == "LL-003"


# ── Markdown table parser ──────────────────────────────────────────────────────

def test_parse_md_table_basic():
    md = textwrap.dedent("""\
        | **ID**     | OBJ-001     |
        | **Status** | Active      |
        | **Owner**  | Captain     |
    """)
    result = _parse_md_table(md)
    assert result["id"] == "OBJ-001"
    assert result["status"] == "Active"
    assert result["owner"] == "Captain"


# ── Prose extractor ────────────────────────────────────────────────────────────

def test_extract_prose_skips_tables():
    md = textwrap.dedent("""\
        | **ID** | OBJ-001 |

        This is the purpose paragraph.

        Another paragraph.
    """)
    prose = _extract_prose(md)
    assert "purpose paragraph" in prose


# ── Objectives parser ─────────────────────────────────────────────────────────

def test_parse_objectives(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_module, "_REPO_ROOT", tmp_path)

    obj_md = textwrap.dedent("""\
        # Objectives

        ## Active Objectives

        ### OBJ-001 -- Build a reliable OS

        | **Field**   | Value      |
        |---|---|
        | **ID**      | OBJ-001    |
        | **Status**  | Active     |
        | **Owner**   | Captain    |
        | **Horizon** | 12 months  |

        **Purpose:** Establish Starship as a production system.

        **Initiatives:**
        - INI-001 -- Core Infrastructure
    """)
    p = tmp_path / "Objectives.md"
    p.write_text(obj_md)

    nodes, edges = _parse_objectives(p)
    assert len(nodes) == 1
    assert nodes[0].node_id == "OBJ-001"
    assert nodes[0].node_type == "objective"
    assert "Starship" in nodes[0].summary


# ── Initiatives parser ────────────────────────────────────────────────────────

def test_parse_initiatives(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_module, "_REPO_ROOT", tmp_path)

    ini_md = textwrap.dedent("""\
        # Initiatives

        ## Active Initiatives

        ### INI-001 -- Core Infrastructure

        | **Field**     | Value   |
        |---|---|
        | **ID**        | INI-001 |
        | **Objective** | OBJ-001 |
        | **Status**    | Active  |
        | **Owner**     | Captain |

        **Goal:** Build the foundational runtime.

        **Missions:**
        - MSN-0001
        - MSN-0002
    """)
    p = tmp_path / "Initiatives.md"
    p.write_text(ini_md)

    nodes, edges = _parse_initiatives(p)
    assert len(nodes) == 1
    assert nodes[0].node_id == "INI-001"
    assert nodes[0].node_type == "initiative"

    edge_rels = [(e.source_id, e.target_id, e.relationship_type) for e in edges]
    assert ("INI-001", "OBJ-001", "pursues") in edge_rels
    assert ("INI-001", "MSN-0001", "contains") in edge_rels
    assert ("INI-001", "MSN-0002", "contains") in edge_rels


# ── Overrides parser ──────────────────────────────────────────────────────────

def test_parse_overrides(tmp_path):
    yaml_text = textwrap.dedent("""\
        mission_initiatives:
          MSN-0001: INI-001
          MSN-0002: INI-002

        adr_objectives:
          ADR-001: OBJ-001
    """)
    p = tmp_path / "overrides.yaml"
    p.write_text(yaml_text)

    edges = _parse_overrides(p)
    rels = {(e.source_id, e.target_id, e.relationship_type) for e in edges}
    # mission_initiatives: ini_id is source, msn_id is target (initiative contains mission)
    assert ("INI-001", "MSN-0001", "contains") in rels
    assert ("INI-002", "MSN-0002", "contains") in rels
    # adr_objectives: adr_id is source, obj_id is target
    assert ("ADR-001", "OBJ-001", "governed_by") in rels
