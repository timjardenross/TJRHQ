"""core/platform/bom_attention.py — platform-assigned attention level for BOM
warnings (BOM supplies no AWS tier, so severity stays 'unknown')."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))
import bom_attention as ba


@pytest.mark.parametrize("headline,alert_type,expected", [
    ("Tropical Cyclone Warning for Queensland east coast", "cyclone", "high"),
    ("Severe Thunderstorm Warning for Sydney Metropolitan", "storm", "high"),
    ("Severe Weather Warning for Damaging Winds", "severe_weather", "high"),
    ("Tsunami Warning for Lord Howe Island", "tsunami", "high"),
    ("Tsunami Warning: No Threat to Australia", "tsunami", "standard"),
    ("Major Flood Warning for the Hawkesbury River", "flood", "high"),
    ("Moderate Flood Warning for the Macleay River", "flood", "high"),
    ("Minor Flood Warning for the Tumut River", "flood", "standard"),
    ("Flood Warning for the Murray River", "flood", "standard"),
    ("Flood Watch for the Southeast Coast", "flood", "standard"),
    ("Fire Weather Warning for Greater Hunter", "bushfire", "standard"),
    ("Gale Warning", "storm", "standard"),
    ("", None, "standard"),
    (None, None, "standard"),
])
def test_attention_level(headline, alert_type, expected):
    assert ba.attention_level(headline, alert_type) == expected


def test_cyclone_type_alone_is_high_even_without_the_phrase():
    assert ba.attention_level("Advice for Coastal Communities", "cyclone") == "high"


def test_labels():
    assert ba.attention_label("high") == "High attention"
    assert ba.attention_label("standard") == "Standard"


# --- emails for high-attention BOM warnings (intelligence/emergency_alerts.py) ---

from unittest.mock import patch

import intelligence.emergency_alerts as ea


def _bom_row(**o):
    base = {"id": "b1", "headline": "Severe Thunderstorm Warning for Sydney Metropolitan", "jurisdiction": "NSW",
            "alert_type": "storm", "location": None, "description": "Damaging winds <b>possible</b>.\nTake shelter.",
            "raw_text": "Body text\n\nhttps://www.bom.gov.au/products/IDN36400.shtml", "issued_at": "2026-11-01T10:00:00+11:00",
            "latitude": None, "longitude": None}
    base.update(o)
    return base


def _site(**o):
    base = {"name": "Chatswood", "site_type": "Branch", "suburb": "Chatswood", "state": "NSW", "postcode": "2067",
            "priority": "Tier 1", "latitude": None, "longitude": None, "geocode_quality": "none"}
    base.update(o)
    return base


def _send(rows, sites, silences=None, send_ok=True):
    with patch.object(ea, "supabase_get", return_value=rows), \
         patch.object(ea.alert_silences, "list_active_silences", return_value=silences or []), \
         patch.object(ea.site_matching, "list_active_sites", return_value=sites), \
         patch.object(ea, "_supabase_request") as mark, \
         patch.object(ea, "send_email", return_value=send_ok) as send:
        n = ea._send_bom_attention_emails("bom_nsw")
    return n, send, mark


def test_high_attention_bom_warning_is_emailed_with_honest_labelling_and_state_sites():
    n, send, mark = _send([_bom_row()], [_site(), _site(name="Dubbo", suburb="Dubbo", postcode="2830", priority="Tier 3")])
    assert n == 1
    kw = send.call_args.kwargs
    assert kw["subject"].startswith("[BOM-HIGH] NSW - Severe Thunderstorm")
    assert "does not give this warning" in kw["html"] and "platform’s own label" in kw["html"]
    assert "Our sites in NSW:</strong> 2 (1 Tier 1)" in kw["html"]
    assert "&lt;b&gt;possible&lt;/b&gt;" in kw["html"] and "<b>possible</b>" not in kw["html"]
    assert 'href="https://www.bom.gov.au/products/IDN36400.shtml"' in kw["html"]
    assert mark.call_count == 2  # sent flag + tier/wording metadata  # dedupe flag set


def test_standard_attention_warning_is_not_emailed():
    n, send, _ = _send([_bom_row(headline="Fire Weather Warning for Greater Hunter", alert_type="bushfire")], [_site()])
    assert n == 0
    send.assert_not_called()


def test_silenced_bom_warning_is_skipped_without_marking_sent():
    sil = {"id": "s1", "reason": "test", "match_jurisdiction": "NSW", "match_alert_type": None, "match_severity": None,
           "match_source_key": None, "starts_at": "2000-01-01T00:00:00+00:00", "ends_at": "2999-01-01T00:00:00+00:00"}
    n, send, mark = _send([_bom_row()], [_site()], silences=[sil])
    assert n == 0
    send.assert_not_called()
    mark.assert_not_called()


def test_failed_send_does_not_set_dedupe_flag():
    n, _, mark = _send([_bom_row()], [_site()], send_ok=False)
    assert n == 0
    # A failure is recorded (migration 0243) but the sent flag is never set.
    bodies = [c.kwargs.get("body") or {} for c in mark.call_args_list]
    assert all("emergency_email_sent_at" not in b for b in bodies)
    assert any("emergency_email_failed_at" in b for b in bodies)


def test_unreadable_site_register_still_sends_without_site_context():
    with patch.object(ea, "supabase_get", return_value=[_bom_row()]), \
         patch.object(ea.alert_silences, "list_active_silences", return_value=[]), \
         patch.object(ea.site_matching, "list_active_sites", side_effect=RuntimeError("down")), \
         patch.object(ea, "_supabase_request"), \
         patch.object(ea, "send_email", return_value=True) as send:
        assert ea._send_bom_attention_emails("bom_nsw") == 1
    assert "Our sites in" not in send.call_args.kwargs["html"]


def test_run_source_only_checks_bom_emails_when_a_high_attention_warning_is_active():
    from types import SimpleNamespace

    from intelligence.ingestion.emergency_alert_adapters.base import CanonicalAlert

    def run(headline):
        a = CanonicalAlert(source_key="bom_nsw", jurisdiction="NSW", headline=headline, event_key="e1", alert_type="storm", severity="unknown")
        adapters = {"bom_nsw": (SimpleNamespace(fetch=lambda: [a]), "emergency_alert_bom_nsw")}
        with patch.object(ea, "_ADAPTERS", adapters), patch.object(ea, "_upsert_batch"), \
             patch.object(ea, "_expire_stale", return_value=0), patch.object(ea, "_record_heartbeat"), \
             patch.object(ea, "_send_bom_attention_emails", return_value=1) as bom:
            return ea.run_source("bom_nsw"), bom

    result, bom = run("Severe Thunderstorm Warning for Sydney")
    bom.assert_called_once_with("bom_nsw")
    assert result["emails_sent"] == 1
    _, bom2 = run("Fire Weather Warning for Greater Hunter")
    bom2.assert_not_called()


def test_state_site_summary():
    import site_matching as sm
    assert sm.state_site_summary("NSW", [_site(), _site(priority="Tier 3"), _site(state="VIC")]) == {"total": 2, "tier1": 1}
    assert sm.state_site_summary("TAS", [_site()]) == {"total": 0, "tier1": 0}


def test_email_names_the_sites_inside_the_warned_area_instead_of_a_state_count():
    import bom_areas

    row = _bom_row()
    sites = [_site(id="s1", name="Dalby Branch", suburb="Dalby", state="QLD"), _site(id="s2", name="Far Away", state="QLD")]
    fake = bom_areas.AreaResult("matched", ["Lower Condamine River"], [sites[0]], 0)
    with patch.object(ea.bom_areas, "match_alert", return_value=fake):
        n, send, _ = _send([row], sites)
    html = send.call_args.kwargs["html"]
    assert n == 1 and "1 of our sites are inside the area BOM names" in html and "Dalby Branch" in html
    assert "Our sites in NSW" not in html


def test_no_email_when_the_named_area_is_known_and_no_site_is_inside_it():
    import bom_areas

    fake = bom_areas.AreaResult("none_inside", ["Barcoo River to Isisford"], [], 0)
    with patch.object(ea.bom_areas, "match_alert", return_value=fake):
        n, send, _ = _send([_bom_row()], [_site(id="s1")])
    assert n == 0 and not send.called  # left for the daily digest


def test_unresolvable_area_in_a_state_with_sites_still_emails():
    import bom_areas

    with patch.object(ea.bom_areas, "match_alert", return_value=bom_areas.AreaResult("unparsed")):
        n, send, _ = _send([_bom_row()], [_site(id="s1")])
    assert n == 1 and send.call_args.kwargs["subject"].startswith("[BOM-HIGH] NSW - ")


_REAL_BOM_TEXT = (
    "Warnings Information\n\n   About Severe Weather Warning Services\n\n\n\nIDV21033\n\nAustralian Government Bureau of Meteorology\n\n"
    "TOP PRIORITY FOR IMMEDIATE BROADCAST\n\nSevere Thunderstorm Warning\n\nIssued at 2:38 pm Monday, 2 November 2026.\n\nSevere thunderstorms developing."
)


def test_bom_text_starts_at_the_warning_and_issued_comes_from_the_text():
    cleaned = ea._clean_bom_text(_REAL_BOM_TEXT)
    assert cleaned.startswith("Severe Thunderstorm Warning") and "About Severe Weather Warning Services" not in cleaned
    assert ea._issued_text({"description": _REAL_BOM_TEXT}) == "2:38 pm Monday, 2 November 2026"
    assert ea._issued_text({"issued_at": "2026-11-02T03:38:00Z", "description": ""}) == "2026-11-02T03:38:00Z"


def test_long_bom_text_is_cut_at_a_paragraph_not_mid_sentence():
    long = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(40))
    out = ea._clean_bom_text(long)
    assert len(out) < 4000 and out.endswith("[Shortened - see the official warning for the full text.]")
    assert "Paragraph" in out.split("\n\n")[-2][:12]


def test_site_label_does_not_repeat_the_suburb():
    assert ea._site_label({"name": "Bendigo", "suburb": "Bendigo"}) == "Bendigo"
    assert ea._site_label({"name": "Norwest Branch", "suburb": "Bella Vista"}) == "Norwest Branch (Bella Vista)"


def test_unresolved_bom_area_says_how_many_sites_could_be_inside():
    import bom_areas

    with patch.object(ea.bom_areas, "match_alert", return_value=bom_areas.AreaResult("unparsed")):
        _n, send, _ = _send([_bom_row()], [_site(id="s1")])
    text = send.call_args.kwargs["text"]
    assert text.startswith("No site matched this alert") and "could be inside it" in text.split("Alert-ID")[0]
