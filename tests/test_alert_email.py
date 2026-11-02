"""core/platform/alert_email.py - subjects, header block, routing rules."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))

import alert_email as ae


def test_subject_is_ascii_tagged_and_keeps_the_site_phrase():
    s = ae.build_subject(ae.EW, "NSW", "Bush fire at Katoomba", n_sites=1, tier1=1)
    assert s == "[EW] NSW - Bush fire at Katoomba [1 site possibly affected, 1 Tier 1]"
    assert s.isascii()
    assert ae.build_subject(ae.LIFTED, "QLD", "Flood").endswith("QLD - Flood")


def test_fields_block_is_stable_and_escaped():
    row = {"id": "a1", "severity": "emergency_warning", "jurisdiction": "NSW", "headline": "Fire <b>x</b>", "location": None,
           "issued_at": "2026-11-02T01:00:00Z", "canonical_url": "https://x"}
    block = ae.fields_block(ae.EW, row, {"Sites-Inside": 2})
    lines = block.split("\n")
    assert "Alert-ID: a1" in lines[0]
    assert "Notice: EW" in lines[1] and "Tier: Emergency Warning" in lines[2]
    assert "Headline: Fire &lt;b&gt;x&lt;/b&gt;" in block and "Location: -" in block and "Sites-Inside: 2" in block


def test_routing_rules():
    assert ae.watch_and_act_should_email(1) and not ae.watch_and_act_should_email(0)
    assert ae.bom_should_email("matched", 0)
    assert not ae.bom_should_email("none_inside", 97)
    assert ae.bom_should_email("unparsed", 97) and not ae.bom_should_email("unparsed", 0)


def test_content_hash_ignores_whitespace_and_case_but_not_words():
    a = {"headline": "Fire at X", "description": "Leave now"}
    assert ae.content_hash(a) == ae.content_hash({"headline": "fire   at x", "description": "LEAVE now"})
    assert ae.content_hash(a) != ae.content_hash({"headline": "Fire at X", "description": "Stay put"})


def test_tier_rank_orders_escalation():
    assert ae.tier_rank("emergency_warning") > ae.tier_rank("watch_and_act") > ae.tier_rank("advice") > ae.tier_rank("unknown")
