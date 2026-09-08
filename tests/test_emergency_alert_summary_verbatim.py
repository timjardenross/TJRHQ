"""HQ V1 Integration QA §7/§9 regression: the hourly Emergency Alert Hub
digest email must preserve official headline/jurisdiction wording verbatim
for urgent-tier alerts, regardless of how the LLM paraphrases the summary
prose. See intelligence/emergency_alert_summary.py's _verbatim_urgent_section.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence.emergency_alert_summary import _verbatim_urgent_section


def _alert(**overrides):
    base = {
        "id": "a1",
        "jurisdiction": "NSW",
        "alert_type": "bushfire",
        "severity": "advice",
        "status": "active",
        "headline": "Advice — grass fire near Test Town",
        "location": None,
        "description": None,
        "issued_at": None,
    }
    base.update(overrides)
    return base


def test_no_urgent_alerts_produces_empty_section():
    alerts = [_alert(severity="advice"), _alert(severity="unknown")]
    assert _verbatim_urgent_section(alerts) == ""


def test_emergency_warning_headline_survives_verbatim():
    alerts = [_alert(
        severity="emergency_warning",
        jurisdiction="VIC",
        headline="EMERGENCY WARNING: Leave now for Test Ridge",
        location="Test Ridge",
    )]
    html = _verbatim_urgent_section(alerts)
    assert "EMERGENCY WARNING: Leave now for Test Ridge" in html
    assert "VIC" in html
    assert "Test Ridge" in html


def test_watch_and_act_included_advice_excluded():
    alerts = [
        _alert(severity="watch_and_act", headline="Watch and Act — Test Creek"),
        _alert(severity="advice", headline="Advice only — should not appear"),
    ]
    html = _verbatim_urgent_section(alerts)
    assert "Watch and Act — Test Creek" in html
    assert "Advice only — should not appear" not in html


def test_multiple_urgent_alerts_each_appear():
    alerts = [
        _alert(id="a1", severity="emergency_warning", jurisdiction="NSW", headline="Emergency Warning A"),
        _alert(id="a2", severity="watch_and_act", jurisdiction="QLD", headline="Watch and Act B"),
    ]
    html = _verbatim_urgent_section(alerts)
    assert "Emergency Warning A" in html
    assert "Watch and Act B" in html
