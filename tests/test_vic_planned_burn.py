"""VIC adapter: planned burns are dropped like every other jurisdiction."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence.ingestion.emergency_alert_adapters import vic_emergency


def test_planned_burn_detected_in_type_or_name():
    assert vic_emergency._is_planned_burn({"incidentType": "PLANNED BURN", "name": "x"})
    assert vic_emergency._is_planned_burn({"incidentType": "GRASS", "name": "Burn off near Ballan"})


def test_real_fires_are_not_planned_burns():
    assert not vic_emergency._is_planned_burn({"incidentType": "BUSH", "name": "Fire near Ballan"})
    assert not vic_emergency._is_planned_burn({"incidentType": None, "name": None})
