"""core/platform/alert_email.py - subjects, header block, routing rules."""

from __future__ import annotations

import re
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


def test_header_block_has_source_and_sent_at_after_the_original_keys():
    block = ae.fields_block(ae.EW, {"id": "a1", "severity": "emergency_warning", "jurisdiction": "NSW", "headline": "h", "source_key": "nsw_rfs"})
    body = re.sub(r"<pre[^>]*>|</pre>", "", block)
    keys = [line.split(":")[0] for line in body.split("\n") if ":" in line]
    assert keys[:8] == ["Alert-ID", "Notice", "Tier", "Jurisdiction", "Headline", "Location", "Issued", "Official-Link"]
    assert keys[8:10] == ["Source", "Sent-At"] and "Source: nsw_rfs" in block


def test_plain_text_twin_keeps_lines_links_and_list_items():
    markup = '<pre>Alert-ID: a1\nNotice: EW</pre><p>Leave <b>now</b>.<br>Second line</p><p><a href="https://x.example/w">Official source</a></p><ul><li>Tier 1 - Dalby</li><li>Tier 2 - Chinchilla</li></ul>'
    text = ae.html_to_text(markup)
    assert "Alert-ID: a1\nNotice: EW" in text and "Leave now.\nSecond line" in text
    assert "Official source (https://x.example/w)" in text
    assert "- Tier 1 - Dalby\n- Tier 2 - Chinchilla" in text and "<" not in text


def test_subject_names_up_to_two_tier1_sites():
    s = ae.build_subject(ae.EW, "NSW", "Fire", 4, 3, ["Dalby", "Chinchilla", "Warwick"])
    assert s.endswith("[4 sites possibly affected, 3 Tier 1: Dalby, Chinchilla +1]")
    assert ae.build_subject(ae.EW, "NSW", "Fire", 2, 0, []).endswith("[2 sites possibly affected]")


def test_sites_banner_leads_with_the_count_tier1_and_names():
    sites = [{"name": "Bendigo", "suburb": "Bendigo", "priority": "Tier 1"}, {"name": "Horsham", "suburb": "Horsham", "priority": "Tier 1"},
             {"name": "Mildura", "suburb": "Mildura", "priority": "Tier 3"}]
    box = ae.sites_banner(sites, "inside the area BOM names")
    text = ae.html_to_text(box)
    assert "3 of our sites inside the area BOM names - 2 Tier 1" in text
    assert "Tier 1: Bendigo, Horsham; Tier 3: Mildura" in text and "#A23A34" in box  # red: a Tier 1 site is in it
    assert "#8A5A1B" in ae.sites_banner([sites[2]])


def test_sites_banner_caps_names_and_says_when_nothing_matched_or_unreadable():
    many = [{"name": f"Site {i}", "suburb": "", "priority": "Tier 2"} for i in range(9)]
    assert "(+3 more, listed below)" in ae.html_to_text(ae.sites_banner(many))
    none = ae.html_to_text(ae.sites_banner([]))
    assert "No site matched this alert" in none and "not proof" in none
    assert "impact unknown" in ae.html_to_text(ae.sites_banner([], register_ok=False))
    assert "97 QLD sites" in ae.html_to_text(ae.sites_banner([], fallback="97 QLD sites could be inside it."))
