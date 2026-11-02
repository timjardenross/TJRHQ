"""core/platform/alert_email.py - subjects, header block, routing rules."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))

import alert_email as ae


def test_subject_is_ascii_tagged():
    s = ae.build_subject(ae.EW, "NSW", "Bush fire at Katoomba")
    assert s == "[EW] NSW - Bush fire at Katoomba" and s.isascii()
    assert ae.build_subject(ae.LIFTED, "QLD", "Flood") == "[LIFTED] QLD - Flood"


def test_fields_block_is_stable_and_escaped():
    row = {"id": "a1", "severity": "emergency_warning", "jurisdiction": "NSW", "headline": "Fire <b>x</b>", "location": None,
           "issued_at": "2026-11-02T01:00:00Z", "canonical_url": "https://x"}
    block = ae.fields_block(ae.EW, row, {"Sites-Inside": 2})
    lines = block.split("\n")
    assert "Alert-ID: a1" in lines[0]
    assert "Notice: EW" in lines[1] and "Tier: Emergency Warning" in lines[2]
    assert "Headline: Fire &lt;b&gt;x&lt;/b&gt;" in block and "Location: -" in block and "Sites-Inside: 2" in block


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
