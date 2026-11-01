"""Tests for core/platform/site_matching.py (migration 0240) — matching an
alert to the organisation's own sites by distance or by named suburb/postcode,
without ever presenting a coarse match as exact."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))
import site_matching as sm


def _site(name="Test Branch", suburb="Katoomba", state="NSW", postcode="2780", priority="Tier 3",
          lat=-33.7134, lon=150.3119, quality="address") -> dict:
    return {"name": name, "suburb": suburb, "state": state, "postcode": postcode, "priority": priority,
            "latitude": lat, "longitude": lon, "geocode_quality": quality}


def _alert(**overrides) -> dict:
    base = {"jurisdiction": "NSW", "severity": "emergency_warning", "headline": "Bush fire", "location": None,
            "latitude": None, "longitude": None}
    base.update(overrides)
    return base


class TestHaversine:
    def test_zero_distance(self):
        assert sm.haversine_km(-33.8, 151.2, -33.8, 151.2) == 0

    def test_sydney_to_melbourne_about_713km(self):
        assert 700 < sm.haversine_km(-33.8688, 151.2093, -37.8136, 144.9631) < 725


class TestDistanceMatch:
    def test_within_radius_matches(self):
        # ~11 km north of the site, inside the 30 km emergency radius
        m = sm.match_alert(_alert(latitude=-33.6134, longitude=150.3119), [_site()])
        assert len(m) == 1 and m[0].method == "distance" and 10 < m[0].distance_km < 12

    def test_outside_radius_does_not_match(self):
        assert sm.match_alert(_alert(latitude=-33.0, longitude=150.3119), [_site()]) == []

    def test_advice_uses_smaller_radius(self):
        a = dict(latitude=-33.5134, longitude=150.3119)  # ~22 km away
        assert sm.match_alert(_alert(**a), [_site()])
        assert sm.match_alert(_alert(severity="advice", **a), [_site()]) == []

    def test_coarse_geocode_widens_reach(self):
        a = _alert(severity="advice", latitude=-33.5134, longitude=150.3119)  # ~22 km, advice radius 15
        assert sm.match_alert(a, [_site(quality="address")]) == []
        assert sm.match_alert(a, [_site(quality="postcode")])  # 15 + 8 pad = 23 km reach

    def test_does_not_require_same_state_for_distance(self):
        # border sites: a Queensland fire can threaten a NSW site
        s = _site(state="NSW")
        assert sm.match_alert(_alert(jurisdiction="QLD", latitude=-33.7, longitude=150.31), [s])


class TestTextMatch:
    def test_suburb_in_location_matches_same_state(self):
        m = sm.match_alert(_alert(location="Katoomba, NSW"), [_site()])
        assert len(m) == 1 and m[0].method == "text" and m[0].distance_km is None

    def test_postcode_in_text_matches(self):
        assert sm.match_alert(_alert(headline="Fire near 2780"), [_site()])

    def test_other_state_not_matched_by_text(self):
        assert sm.match_alert(_alert(jurisdiction="VIC", location="Katoomba"), [_site()]) == []

    def test_substring_of_another_word_not_matched(self):
        assert sm.match_alert(_alert(location="Katoombaville area"), [_site()]) == []

    def test_short_suburb_names_ignored(self):
        assert sm.match_alert(_alert(location="Ayr district"), [_site(suburb="Ayr", state="NSW", lat=None, lon=None, quality="none")]) == []

    def test_ungeocoded_site_falls_back_to_text_even_with_alert_point(self):
        s = _site(lat=None, lon=None, quality="none")
        m = sm.match_alert(_alert(latitude=-33.7, longitude=150.3, location="Katoomba"), [s])
        assert len(m) == 1 and m[0].method == "text"

    def test_no_signal_no_match(self):
        assert sm.match_alert(_alert(location="Somewhere else"), [_site()]) == []


class TestOrdering:
    def test_tier1_before_tier3_then_nearest(self):
        a = _alert(latitude=-33.7134, longitude=150.3119)
        near3 = _site(name="near-t3", priority="Tier 3")
        far1 = _site(name="far-t1", priority="Tier 1", lat=-33.60, lon=150.31)
        near1 = _site(name="near-t1", priority="Tier 1", lat=-33.70, lon=150.31)
        names = [m.site["name"] for m in sm.match_alert(a, [near3, far1, near1])]
        assert names == ["near-t1", "far-t1", "near-t3"]


class TestStatesWithoutSiteMatch:
    def test_counts_unmatched_alerts_only_where_we_have_sites(self):
        sites = [_site()]
        alerts = [
            _alert(location="Katoomba"),              # matched
            _alert(location="Dubbo"),                 # NSW, unmatched
            _alert(jurisdiction="TAS", location="x"), # no TAS sites -> not reported
        ]
        assert sm.states_without_site_match(alerts, sites) == {"NSW": 1}


class TestEmergencyEmailSiteContext:
    """intelligence/emergency_alerts.py attaches matched sites to the email."""

    def _run(self, sites, row_overrides=None):
        from unittest.mock import patch

        import intelligence.emergency_alerts as ea

        row = {"id": "a1", "headline": "Emergency Warning <b>Katoomba</b>", "jurisdiction": "NSW", "alert_type": "bushfire",
               "location": "Katoomba, NSW", "description": "d", "canonical_url": None, "issued_at": None,
               "latitude": None, "longitude": None, **(row_overrides or {})}
        with patch.object(ea, "supabase_get", return_value=[row]), \
             patch.object(ea.alert_silences, "list_active_silences", return_value=[]), \
             patch.object(ea.site_matching, "list_active_sites", return_value=sites), \
             patch.object(ea, "_supabase_request"), \
             patch.object(ea, "send_email", return_value=True) as send:
            ea._send_emergency_warning_emails("nsw_rfs")
        return send.call_args.kwargs

    def test_subject_and_body_name_matched_sites(self):
        sent = self._run([_site(priority="Tier 1", name="Katoomba <Biz>")])
        assert "1 site possibly affected, 1 Tier 1" in sent["subject"]
        assert "Katoomba &lt;Biz&gt;" in sent["html"] and "<Biz>" not in sent["html"]

    def test_no_match_says_so_without_claiming_safety(self):
        sent = self._run([_site(suburb="Dubbo", postcode="2830")])
        assert "possibly affected" not in sent["subject"]
        assert "none matched by location" in sent["html"]

    def test_unreadable_register_sends_without_site_section(self):
        from unittest.mock import patch

        import intelligence.emergency_alerts as ea

        row = {"id": "a1", "headline": "h", "jurisdiction": "NSW", "alert_type": "bushfire", "location": "x",
               "description": "d", "canonical_url": None, "issued_at": None, "latitude": None, "longitude": None}
        with patch.object(ea, "supabase_get", return_value=[row]), \
             patch.object(ea.alert_silences, "list_active_silences", return_value=[]), \
             patch.object(ea.site_matching, "list_active_sites", side_effect=RuntimeError("down")), \
             patch.object(ea, "_supabase_request"), \
             patch.object(ea, "send_email", return_value=True) as send:
            assert ea._send_emergency_warning_emails("nsw_rfs") == 1
        assert "Sites" not in send.call_args.kwargs["html"]
