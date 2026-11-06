"""CAP feeds we enrich from, validated against the real CAP 1.2 and CAP-AU v3.0 XSDs (tests/fixtures/cap_schemas).

Measured 2026-11-06 on live captures: NSW RFS, SA CFS and the BoM-via-WMO fixtures are valid CAP-AU; a live BoM
Bushwalkers Weather Alert uses an <event> outside the CAP-AU list (valid CAP 1.2, not CAP-AU); the QLD storm/flood/
cyclone feed writes '...+00:00+10:00' timestamps that are valid in neither. The last two are exercised here by
altering a real fixture message the same way, so the difference stays documented and tested.
Skipped when lxml (not a project requirement) is unavailable."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

lxml_etree = pytest.importorskip("lxml.etree")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.emergency_alert_helpers import FIXTURE_ROOT, block_network  # noqa: F401

pytestmark = pytest.mark.usefixtures("block_network")

SCHEMAS = Path(__file__).resolve().parent / "fixtures" / "cap_schemas"
CAP = "{urn:oasis:names:tc:emergency:cap:1.2}"
CAP12 = lxml_etree.XMLSchema(lxml_etree.parse(str(SCHEMAS / "CAP-v1.2.xsd")))
CAPAU = lxml_etree.XMLSchema(lxml_etree.parse(str(SCHEMAS / "capauv3-0_schema-v1-1.xsd")))


def _alerts(path: Path):
    """Every CAP <alert> in a file, each re-rooted as its own document (EDXL wrappers are not CAP)."""
    return [lxml_etree.fromstring(lxml_etree.tostring(a)) for a in lxml_etree.parse(str(path)).getroot().iter(CAP + "alert")]


def _fixture_alerts(source: str, pattern: str):
    paths = sorted((FIXTURE_ROOT / source).glob(pattern))
    assert paths, f"no fixtures for {source}/{pattern}"
    return [(p.name, a) for p in paths for a in _alerts(p)]


@pytest.mark.parametrize("source,pattern", [("nsw_rfs", "cap.xml"), ("sa_cfs", "feed.xml"), ("bom_nsw", "cap_*.xml")])
@pytest.mark.parametrize("schema_name,schema", [("CAP 1.2", CAP12), ("CAP-AU v3.0", CAPAU)])
def test_enrichment_fixtures_validate(source, pattern, schema_name, schema):
    for name, alert in _fixture_alerts(source, pattern):
        assert schema.validate(alert), f"{source}/{name} fails {schema_name}: {schema.error_log.last_error}"


def _sample_bom():
    return _alerts(FIXTURE_ROOT / "bom_nsw" / "cap_AusBoM_IDN22000_2026_11_06T05_08_15_00_00.xml")[0]


def test_an_event_outside_the_cap_au_list_is_valid_cap_but_not_cap_au():
    """BoM's Bushwalkers Weather Alert uses <event>Exposure</event>."""
    alert = _sample_bom()
    alert.find(f"{CAP}info/{CAP}event").text = "Exposure"
    assert CAP12.validate(alert) and not CAPAU.validate(alert)


def test_the_qld_double_offset_timestamp_is_invalid_in_both():
    alert = _sample_bom()
    alert.find(CAP + "sent").text = "2026-11-06T09:38:24.158110+00:00+10:00"
    assert not CAP12.validate(alert) and not CAPAU.validate(alert)


def test_cap_au_requires_the_profile_code_that_plain_cap_does_not():
    alert = _sample_bom()
    for code in alert.findall(CAP + "code"):
        alert.remove(code)
    assert CAP12.validate(alert) and not CAPAU.validate(alert)
