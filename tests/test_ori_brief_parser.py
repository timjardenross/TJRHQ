"""
Unit tests for intelligence/ingestion/ori_brief_parser.py (USS-TJR-MSN-0074 WP2).

Uses the ACTUAL content of two real briefs from the source repository to prove
the version-detecting, backward-compatible parser handles both observed formats:
  - v0 (2026-06-06): flat "**Key Events:**" bold pairs, single H1, no YAML
  - v1 (2026-06-19): "## Key Incidents" sections, "**Date:**" line, no YAML
Plus a synthetic v1.0 file with YAML front matter (the forward standard).
"""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.ingestion.ori_brief_parser import (
    parse_brief, split_front_matter, detect_version,
)

# ── Real fixtures (verbatim from the repository) ──────────────────────────────

V0_FILE = "USSTJROS/2026-06-06-daily-operational-resilience-brief.md"
V0_RAW = """# Daily Operational Resilience Intelligence Brief - 2026-06-06

**Key Events:** Cyber incidents in Australia (e.g., Ochre Health, Mackay Sugar).

**CPS 230:** Ongoing implementation.

**Resilience Focus:** Third-party risk management.
"""

V1_FILE = "USSTJROS/2026-06-19-daily-operational-resilience-brief.md"
V1_RAW = """# Daily Operational Resilience Intelligence Brief

**Date:** 2026-06-19

## Key Incidents
- Major Vodafone Australia network outage on June 18 due to hub failure. Affected millions, services mostly restored by late morning.

## Regulatory Context
- CPS 230 amendments effective July 2026.

## Implications and Recommendations
- Strengthen third-party and telco resilience testing.

**Sources:** Public reports.

---

## Summary

The document highlights a significant telecommunications disruption in Australia.
"""

V10_FILE = "briefs/2026/06/2026-06-20-daily-operational-resilience-brief.md"
V10_RAW = """---
date: 2026-06-20
region: Australia
brief_type: operational_resilience
source: grok
version: 1.0
classification: public
---

# Daily Operational Resilience Intelligence Brief — 2026-06-20

## Key Incidents
- AWS ap-southeast-2 elevated error rates affecting Sydney workloads.

## Regulatory Context
- APRA reinforces CPS 230 material service provider expectations.
"""


# v2 = the reconstructed Grok layout under briefs/YYYY/MM/ (2026-06 move)
V2_FILE = "briefs/2026/06/2026-06-19-daily-operational-resilience-brief.md"
V2_RAW = """# Daily Operational Resilience Intelligence Brief

**Date:** 2026-06-19

**Audience:** Banking & Critical Infrastructure Executives

**Focus:**
Australia (Primary)
APAC (Secondary)
Global Flow-On Risks

---

Archive Status: Reconstructed

## Executive Summary
Major Vodafone Australia network outage due to hub failure significantly impacted services, alongside ongoing CPS 230 implementation.

## Key Developments
- Vodafone outage affecting millions.
- CPS 230 regulatory updates.

## Risk Assessment
Telco dependencies pose systemic risks to banking and critical infrastructure.

## Executive Actions
- Assess third-party telco exposures.
- Test failover and communication plans.

## Watchlist (24-72 Hours)
- Full service restoration and lessons learned.

## Source Notes
Reconstructed from task title "Vodafone outage, CPS 230 updates".
"""


class TestParseV2Reconstructed(unittest.TestCase):
    def setUp(self):
        self.b = parse_brief(V2_FILE, V2_RAW)

    def test_date_from_partitioned_path(self):
        self.assertEqual(self.b.brief_date, date(2026, 6, 19))

    def test_key_developments_become_events(self):
        joined = " ".join(i["text"] for i in self.b.candidate_items())
        self.assertIn("Vodafone", joined)
        self.assertIn("CPS 230", joined)

    def test_executive_summary_not_an_event(self):
        for i in self.b.candidate_items():
            self.assertNotIn("significantly impacted", i["text"])

    def test_executive_actions_in_implications(self):
        self.assertIn("third-party telco", self.b.implications_text())

    def test_region_au(self):
        self.assertEqual(self.b.geography, "AU")


class TestFrontMatter(unittest.TestCase):
    def test_no_front_matter(self):
        fm, body = split_front_matter(V0_RAW)
        self.assertEqual(fm, {})
        self.assertTrue(body.startswith("# Daily"))

    def test_yaml_front_matter(self):
        fm, body = split_front_matter(V10_RAW)
        self.assertEqual(fm.get("version"), 1.0)
        self.assertEqual(fm.get("classification"), "public")
        self.assertTrue(body.lstrip().startswith("# Daily"))


class TestVersionDetection(unittest.TestCase):
    def test_v0_flat(self):
        self.assertEqual(detect_version(V0_RAW), "0")

    def test_v1_sections(self):
        self.assertEqual(detect_version(V1_RAW), "1")


class TestParseV0(unittest.TestCase):
    def setUp(self):
        self.b = parse_brief(V0_FILE, V0_RAW)

    def test_date_from_filename(self):
        self.assertEqual(self.b.brief_date, date(2026, 6, 6))

    def test_version(self):
        self.assertEqual(self.b.version, "0")

    def test_region_default_au(self):
        self.assertEqual(self.b.geography, "AU")

    def test_extracts_key_events_and_regulatory(self):
        items = self.b.candidate_items()
        text = " ".join(i["text"] for i in items)
        self.assertIn("Ochre Health", text)
        self.assertIn("CPS 230", text)          # regulatory bold pair captured
        self.assertGreaterEqual(len(items), 2)

    def test_classification_public_default(self):
        self.assertEqual(self.b.classification, "public")


class TestParseV1(unittest.TestCase):
    def setUp(self):
        self.b = parse_brief(V1_FILE, V1_RAW)

    def test_date_from_filename(self):
        self.assertEqual(self.b.brief_date, date(2026, 6, 19))

    def test_version(self):
        self.assertEqual(self.b.version, "1")

    def test_sections_present(self):
        self.assertIn("key_incidents", self.b.sections)
        self.assertIn("regulatory", self.b.sections)

    def test_vodafone_incident_extracted(self):
        items = self.b.candidate_items()
        joined = " ".join(i["text"] for i in items)
        self.assertIn("Vodafone", joined)
        self.assertIn("CPS 230", joined)

    def test_summary_not_an_event(self):
        # Summary section must not become a candidate event.
        for i in self.b.candidate_items():
            self.assertNotIn("highlights a significant", i["text"])

    def test_implications_available(self):
        self.assertIn("resilience testing", self.b.implications_text())


class TestParseV10Yaml(unittest.TestCase):
    def setUp(self):
        self.b = parse_brief(V10_FILE, V10_RAW)

    def test_version_from_yaml(self):
        self.assertEqual(self.b.version, "1.0")

    def test_date_from_filename_wins(self):
        self.assertEqual(self.b.brief_date, date(2026, 6, 20))

    def test_region_from_yaml(self):
        self.assertEqual(self.b.geography, "AU")
        self.assertEqual(self.b.region, "Australia")

    def test_events_extracted(self):
        joined = " ".join(i["text"] for i in self.b.candidate_items())
        self.assertIn("AWS", joined)
        self.assertIn("CPS 230", joined)


class TestNeverRejects(unittest.TestCase):
    def test_empty_body_still_parses(self):
        b = parse_brief("USSTJROS/2026-06-01-daily-operational-resilience-brief.md", "# Title only\n")
        self.assertEqual(b.brief_date, date(2026, 6, 1))
        self.assertIn("no_events", b.warnings)  # recorded, not raised


if __name__ == "__main__":
    unittest.main(verbosity=2)
