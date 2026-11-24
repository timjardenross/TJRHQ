"""Tests for the dated-events extractor and its flag-gated 'Dated events' input to the forward watch (all default OFF).

Fixtures are real collected rows (2026 sample export, text trimmed) plus small synthetic cases for the rules production data did not exercise.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ANALYTICS = (
    Path(__file__).resolve().parent.parent / "tools" / "intelligence" / "analytics"
)
sys.path.insert(0, str(ANALYTICS))

import dated_events as de
import forward_watch as fw

AS_OF = datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc)


def row(eid, source, pub, title, summary=None, collected=None):
    return {
        "event_id": eid,
        "source_name": source,
        "published_at": pub,
        "collected_at": collected or pub,
        "raw_title": title,
        "raw_summary": summary,
    }


def ev(rows, **kw):
    return de.extract_events(rows, **kw)


class TestStatedDates(unittest.TestCase):
    def test_cisa_end_of_life_abbreviated_month(self):
        r = row(
            "c1",
            "CISA Alerts",
            "2026-10-13 12:00:00+00",
            "CISA Urges Patching Newly Exploited Vulnerability in Ivanti Connect Secure",
            "CISA added CVE-2026-104935 to its KEV Catalog on Oct. 13, 2026.&nbsp; Ivanti Connect Secure version 22.8 reaches end of life on Jan. 31, 2027.&nbsp;",
        )
        out = ev([r])
        self.assertEqual(len(out), 1)
        e = out[0]
        self.assertEqual(
            (e["date"], e["kind"], e["date_basis"]),
            ("2027-01-31", "vendor_lifecycle", de.BASIS_EXPLICIT),
        )
        self.assertEqual(e["uncertainty_label"], "OFFICIAL_DATE_STATED")
        self.assertIn("reaches end of life on Jan. 31, 2027", e["evidence_span"])

    def test_vendor_dates_and_past_dates_in_same_row(self):
        r = row(
            "g1",
            "Google Cloud Security Bulletins",
            "2026-11-10 01:46:31+00",
            "GCP-2026-068",
            "Published: 2026-10-14 Updated: 2026-11-05 This vulnerability was patched on August 27, 2026. Integrations created on or after October 15, 2026, must have a run-as service account. Starting January 15, 2027 (UTC), this requirement also applies to existing integrations created before October 15, 2026.",
        )
        out = ev([r])
        self.assertEqual([e["date"] for e in out], ["2027-01-15"])
        self.assertEqual(out[0]["kind"], "vendor_lifecycle")

    def test_cisco_advance_notice_and_next_publication(self):
        r = row(
            "ci1",
            "Cisco Security Advisories",
            "2026-10-28 16:00:00+00",
            "Cisco Advance Notification for Publication of November 4, 2026, Security Advisories",
            "On November 4, 2026, Cisco PSIRT will publish advisories. The next planned publication of advisories for security-hardened releases will be January 20, 2027.",
        )
        out = ev([r])
        self.assertEqual([e["date"] for e in out], ["2026-11-04", "2027-01-20"])
        self.assertTrue(all(e["kind"] == "advisory_deadline" for e in out))

    def test_revision_and_publication_labels_are_not_events(self):
        r = row(
            "f1",
            "Fortinet PSIRT Advisories",
            "2026-11-10 08:00:00+00",
            "Numeric truncation error",
            "CVSSv3 Score: 9.6 vulnerability in FortiOS. Revised on 2026-11-13 00:00:00",
        )
        self.assertEqual(ev([r]), [])

    def test_regulatory_consultation_and_commencement(self):
        rows = [
            row(
                "a1",
                "APRA Consultations",
                "2026-11-02 00:00:00+00",
                "Consultation on prudential standard changes",
                "Submissions close on 12 February 2027. The final standard will commence on 1 July 2027.",
            ),
            row(
                "a2",
                "ASIC Media Releases",
                "2026-11-03 00:00:00+00",
                "ASIC relief",
                "The relief comes into effect on 1 March 2027.",
            ),
        ]
        out = ev(rows)
        self.assertEqual(
            sorted((e["date"], e["kind"]) for e in out),
            [
                ("2027-02-12", "regulatory"),
                ("2027-03-01", "regulatory"),
                ("2027-07-01", "regulatory"),
            ],
        )

    def test_regulatory_cue_from_a_vendor_is_lifecycle_not_regulatory(self):
        r = row(
            "v1",
            "Cisco Security Advisories",
            "2026-11-02 00:00:00+00",
            "Notice",
            "The change takes effect on 1 March 2027.",
        )
        self.assertEqual(ev([r])[0]["kind"], "vendor_lifecycle")

    def test_date_without_cue_is_not_an_event(self):
        r = row(
            "n1",
            "APRA — Speeches and Publications",
            "2026-10-15 13:15:02+00",
            "Life insurance claims and disputes statistics",
            "Published 16 October 2026. Data June 2026 XLSX 918.81 KB ‧ 16 October 2026",
        )
        self.assertEqual(ev([r]), [])

    def test_month_only_is_flagged_and_current_month_is_skipped(self):
        r = row(
            "m1",
            "Cisco Security Advisories",
            "2026-11-02 00:00:00+00",
            "Notice",
            "Support ends: end of support is planned for March 2027. A fix is due by November 2026.",
        )
        out = ev([r])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["uncertainty_label"], "DATE_PRECISION_MONTH")
        self.assertEqual(out[0]["date"], "2027-03-01")

    def test_nvd_excluded_but_kev_due_dates_kept(self):
        # NVD rows carry no forward date; KEV rows carry a stated due date (#730).
        nvd = row("k0", "NVD Recent CVEs", "2026-11-02 00:00:00+00", "CVE-2026-1: Thing",
                  "Apply updates by 30 November 2026 due date.")
        kev = row("k1", "CISA Known Exploited Vulnerabilities", "2026-11-02 00:00:00+00",
                  "CVE-2026-1: Thing", "Apply updates by 30 November 2026 due date.")
        self.assertEqual(ev([nvd]), [])
        self.assertEqual(len(ev([kev])), 1)


class TestMissingPublicationDate(unittest.TestCase):
    """Several regulator feeds (APRA Consultations, Treasury Consultations) are collected with published_at NULL."""

    def test_explicit_dates_use_collection_date_as_reference(self):
        r = row(
            "p1",
            "APRA Consultations",
            None,
            "Streamlining FAR administration",
            "Consultation is now open, until 2 October 2026. APRA and ASIC expect the changes to take effect from early 2027.",
            collected="2026-09-10 00:00:00+00",
        )
        out = ev([r])
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]["date"], out[0]["kind"]), ("2026-10-02", "regulatory"))
        self.assertEqual(
            out[0]["reference_date"], "collected_at (published_at missing)"
        )
        self.assertEqual(out[0]["date_basis"], de.BASIS_EXPLICIT)

    def test_no_inference_and_no_relative_dates_without_a_publication_date(self):
        rows = [
            row(
                "p1",
                "APRA Consultations",
                None,
                "Consultation",
                "Submissions close on 12 October.",
                collected="2026-09-10 00:00:00+00",
            ),
            row(
                "p2",
                "APRA Consultations",
                None,
                "Consultation",
                "Submissions close tomorrow.",
                collected="2026-09-10 00:00:00+00",
            ),
        ]
        self.assertEqual(ev(rows), [])

    def test_no_later_than_cue(self):
        r = row(
            "p3",
            "APRA Consultations",
            None,
            "Consultation",
            "Submissions are requested to be provided no later than 21 August 2026.",
            collected="2026-08-01 00:00:00+00",
        )
        self.assertEqual(ev([r])[0]["date"], "2026-08-21")

    def test_title_only_row_yields_nothing(self):
        r = row(
            "p4",
            "APRA Consultations",
            None,
            "Minor updates to the prudential framework",
            None,
            collected="2026-11-10 00:00:00+00",
        )
        self.assertEqual(ev([r]), [])


class TestAemo(unittest.TestCase):
    def test_forecast_emitted_with_au_day_first_numeric_date(self):
        r = row(
            "e1",
            "AEMO Market Notices",
            "2026-10-09 19:00:23+00",
            "STPASA - Forecast Lack Of Reserve Level 1 (LOR1) in the NSW Region on 12/10/2026",
        )
        out = ev([r])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["date"], "2026-10-12")
        self.assertEqual(out[0]["kind"], "advisory_deadline")
        self.assertEqual(out[0]["uncertainty_label"], "OPERATOR_FORECAST")

    def test_cancellation_removes_matching_forecast_only(self):
        rows = [
            row(
                "e1",
                "AEMO Market Notices",
                "2026-10-05 21:20:35+00",
                "Forecast Minimum System Load MSL1 condition in the SA Region on 10/10/2026",
            ),
            row(
                "e2",
                "AEMO Market Notices",
                "2026-10-05 21:20:35+00",
                "Forecast Minimum System Load MSL1 condition in the SA Region on 11/10/2026",
            ),
            row(
                "e3",
                "AEMO Market Notices",
                "2026-10-08 21:20:35+00",
                "Cancellation of Forecast Minimum System Load (MSL) MSL1 event in the SA Region on 10/10/2026.",
            ),
        ]
        self.assertEqual([e["date"] for e in ev(rows)], ["2026-10-11"])

    def test_forecast_published_after_a_cancellation_survives(self):
        rows = [
            row(
                "e1",
                "AEMO Market Notices",
                "2026-10-17 00:00:00+00",
                "STPASA - Cancellation of the Forecast Lack Of Reserve Level 2 (LOR2) in the SA Region on 20/10/2026",
            ),
            row(
                "e2",
                "AEMO Market Notices",
                "2026-10-17 19:05:25+00",
                "STPASA - Forecast Lack Of Reserve Level 2 (LOR2) in the SA Region on 20/10/2026",
            ),
        ]
        self.assertEqual([e["event_id"] for e in ev(rows)], ["e2"])

    def test_past_tense_and_same_day_notices_are_not_future(self):
        rows = [
            row(
                "e1",
                "AEMO Market Notices",
                "2026-11-09 00:00:00+00",
                "[EventId:202611090300_NRM_SA1_NSW1_started] NEGRES CONSTRAINT NRM_SA1_NSW1 started operating from 09 November 2026 03:00",
            ),
            row(
                "e2",
                "AEMO Market Notices",
                "2026-08-29 00:00:00+00",
                "Direction - SA region 29/08/2026",
            ),
        ]
        self.assertEqual(ev(rows), [])

    def test_aemo_title_without_forecast_wording_is_not_an_event(self):
        r = row(
            "e1",
            "AEMO Market Notices",
            "2026-09-10 00:00:00+00",
            "NON-CONFORMANCE Region QLD1 Friday, 9 October 2026",
        )
        self.assertEqual(ev([r]), [])


class TestProviderMaintenance(unittest.TestCase):
    def test_supabase_window_range_collapses_to_one_event(self):
        r = row(
            "s1",
            "Supabase Status",
            "2026-11-24 01:56:25+00",
            "Maintenance: Scheduled maintenance: Shared Pooler (Supavisor), eu-west-2",
            "Status: Scheduled (Wed, 09 Dec 2026 13:00:00 GMT - Wed, 09 Dec 2026 15:00:00 GMT) We will perform scheduled maintenance on Wednesday, December 9, from 13:00 to 15:00 UTC.",
        )
        out = ev([r])
        self.assertEqual(len(out), 1)
        self.assertEqual(
            (out[0]["date"], out[0]["end_date"], out[0]["kind"]),
            ("2026-12-09", None, "planned_maintenance"),
        )
        self.assertEqual(out[0]["uncertainty_label"], "SCHEDULED_BY_OWNER")
        self.assertEqual(out[0]["date_basis"], de.BASIS_EXPLICIT)

    def test_twilio_window_start_end_and_explicit_year_beats_header(self):
        r = row(
            "t1",
            "Twilio Status",
            "2026-11-07 00:22:04+00",
            "Brazil SMS Carrier Maintenance - TIM",
            "THIS IS A SCHEDULED EVENT Nov 16 , 22:00 - 23:00 PST Scheduled - The TIM network is conducting a planned maintenance from 16 November 2026 at 22:00 PST until 17 November 2026 at 01:00 PST.",
        )
        out = ev([r])
        self.assertEqual(len(out), 1)
        self.assertEqual(
            (out[0]["date"], out[0]["end_date"]), ("2026-11-16", "2026-11-17")
        )
        self.assertEqual(out[0]["date_basis"], de.BASIS_EXPLICIT)
        self.assertEqual(out[0]["uncertainty_label"], "SCHEDULED_BY_OWNER")

    def test_ambiguous_numeric_date_from_a_non_au_source_is_skipped_unambiguous_kept(
        self,
    ):
        rows = [
            row(
                "t1",
                "Twilio Status",
                "2026-11-19 13:07:22+00",
                "TNX-AU1 upgrade",
                "We're conducting a planned maintenance between 5:00 AM and 9:00 AM Pacific Time on 01/22/2027.",
            ),
            row(
                "t2",
                "Twilio Status",
                "2026-11-19 13:07:22+00",
                "TNX-DE1 upgrade",
                "We're conducting a planned maintenance between 3:00 PM and 7:00 PM Pacific Time on 02/12/2027.",
            ),
        ]
        self.assertEqual([e["date"] for e in ev(rows)], ["2027-01-22"])

    def test_completed_notice_and_past_window_are_dropped(self):
        rows = [
            row(
                "s1",
                "Supabase Status",
                "2026-09-15 11:45:07+00",
                "Maintenance: Scheduled Platform Maintenance - 15th September, 2026",
                "Status: Complete The scheduled maintenance has been completed.",
            ),
            row(
                "c1",
                "Cloudflare Status",
                "2026-09-14 20:30:00+00",
                "Cloudflare Status: Network Performance Issues in Ashburn (resolved)",
                "Between 20:55-21:52 UTC on 2026-09-15 elevated errors. The issue has been resolved.",
            ),
        ]
        self.assertEqual(ev(rows), [])

    def test_window_that_started_before_publication_is_not_emitted(self):
        r = row(
            "a1",
            "Akamai Status",
            "2026-09-22 00:30:17+00",
            "Akamai Status: Increased latency during upstream provider maintenance (investigating)",
            "Scheduled upstream provider maintenance is taking place from September 18, 2026 at 06:30 UTC through October 3, 2026 at 23:59 UTC.",
        )
        self.assertEqual(ev([r]), [])


class TestInferredAndRelative(unittest.TestCase):
    def test_year_taken_from_publication_date_is_labelled(self):
        r = row(
            "i1",
            "ACSC Alerts & Advisories",
            "2026-10-22 05:17:11+00",
            "Notice",
            "The new rules will come into effect on 20 November and limit chores.",
        )
        out = ev([r])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["date"], "2026-11-20")
        self.assertEqual(out[0]["date_basis"], de.BASIS_INFERRED)
        self.assertEqual(out[0]["uncertainty_label"], "INFERRED_YEAR")

    def test_year_less_date_already_passed_is_not_rolled_forward_a_year(self):
        r = row(
            "i1",
            "ACSC Alerts & Advisories",
            "2026-11-24 05:17:11+00",
            "Notice",
            "The change came into effect on 3 September and the service will be unavailable.",
        )
        self.assertEqual(ev([r]), [])

    def test_year_less_date_rolls_to_next_year_only_when_close(self):
        r = row(
            "i1",
            "Cisco Security Advisories",
            "2026-12-20 00:00:00+00",
            "Notice",
            "End of support for the appliance is 10 January.",
        )
        out = ev([r])
        self.assertEqual(
            (out[0]["date"], out[0]["uncertainty_label"]),
            ("2027-01-10", "INFERRED_YEAR"),
        )

    def test_lowercase_month_word_is_not_a_date(self):
        r = row(
            "i1",
            "Cisco Security Advisories",
            "2026-11-02 00:00:00+00",
            "Notice",
            "End of support, which may 5 times extend, is pending.",
        )
        self.assertEqual(ev([r]), [])

    def test_relative_date_resolves_against_verified_publication_only(self):
        r = row(
            "r1",
            "Supabase Status",
            "2026-11-24 01:00:00+00",
            "Maintenance notice",
            "We will perform maintenance tomorrow on the pooler.",
        )
        out = ev([r])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["date"], "2026-11-25")
        self.assertEqual(out[0]["uncertainty_label"], "RELATIVE_DATE_LOWER_CONFIDENCE")
        self.assertEqual(out[0]["date_basis"], de.BASIS_INFERRED)

    def test_relative_date_next_week_and_weekday(self):
        rows = [
            row(
                "r1",
                "Supabase Status",
                "2026-11-24 01:00:00+00",
                "Maintenance notice",
                "Planned maintenance next week on the pooler.",
            ),
            row(
                "r2",
                "Supabase Status",
                "2026-11-24 01:00:00+00",
                "Maintenance notice 2",
                "Planned maintenance next Friday on the pooler.",
            ),
        ]
        out = {e["event_id"]: e for e in ev(rows)}
        self.assertEqual(
            (out["r1"]["date"], out["r1"]["precision"]), ("2026-11-30", "week")
        )
        self.assertEqual(out["r2"]["date"], "2026-11-27")

    def test_relative_date_refused_for_aggregator_unverified_or_cueless(self):
        rows = [
            row(
                "r1",
                "Google News - Telstra",
                "2026-11-24 01:00:00+00",
                "Telstra planned maintenance tomorrow",
            ),
            row(
                "r2",
                "Supabase Status",
                "2026-11-24 03:00:00+00",
                "Maintenance tomorrow",
                None,
                collected="2026-11-24 01:00:00+00",
            ),
            row(
                "r3",
                "Supabase Status",
                "2026-11-24 01:00:00+00",
                "Update",
                "We will see you tomorrow.",
            ),
        ]
        self.assertEqual(ev(rows, include_news=True), [])


class TestNews(unittest.TestCase):
    def setUp(self):
        self.r = row(
            "n1",
            "Guardian Australia",
            "2026-10-22 05:17:11+00",
            "Airbnb guests freed from chores",
            "The changes will come into effect on 20 November 2026.",
        )

    def test_news_skipped_by_default(self):
        self.assertEqual(ev([self.r]), [])

    def test_news_labelled_when_included(self):
        out = ev([self.r], include_news=True)
        self.assertEqual(out[0]["uncertainty_label"], "RELAYED_BY_NEWS")


class TestHelpers(unittest.TestCase):
    def test_upcoming_window(self):
        rows = [
            row(
                "s1",
                "Supabase Status",
                "2026-11-13 03:36:00+00",
                "Scheduled maintenance A",
                "Status: Scheduled (Mon, 30 Nov 2026 13:00:00 GMT - Mon, 30 Nov 2026 15:00:00 GMT)",
            ),
            row(
                "s2",
                "Supabase Status",
                "2026-11-13 03:36:00+00",
                "Scheduled maintenance B",
                "Status: Scheduled (Mon, 01 Feb 2027 13:00:00 GMT - Mon, 01 Feb 2027 15:00:00 GMT)",
            ),
        ]
        up = de.upcoming(ev(rows), AS_OF, 30)
        self.assertEqual([e["event_id"] for e in up], ["s1"])

    def test_latest_per_notice_keeps_one(self):
        e1 = {
            "source": "S",
            "event": "X",
            "date": "2026-12-01",
            "kind": "planned_maintenance",
            "published_at": "2026-11-01T00:00:00+00:00",
            "event_id": "a",
        }
        e2 = dict(e1, published_at="2026-11-02T00:00:00+00:00", event_id="b")
        self.assertEqual([e["event_id"] for e in de.latest_per_notice([e1, e2])], ["b"])

    def test_statuspage_adapter_keeps_only_open_windows(self):
        payload = {
            "scheduled_maintenances": [
                {
                    "id": "m1",
                    "name": "Monthly maintenance",
                    "status": "scheduled",
                    "created_at": "2026-10-07T10:36:37.997+11:00",
                    "updated_at": "2026-10-07T10:36:37.997+11:00",
                    "shortlink": "https://stspg.io/x",
                    "incident_updates": [
                        {
                            "body": "10:00 pm AEDT Saturday, 5 December 2026 to 7:00 am AEDT Monday, 7 December 2026"
                        }
                    ],
                },
                {"id": "m2", "name": "Old", "status": "completed"},
            ]
        }
        rows = de.rows_from_statuspage_maintenances(payload)
        self.assertEqual(len(rows), 1)
        out = ev(rows)
        self.assertEqual(
            (out[0]["date"], out[0]["end_date"]), ("2026-12-05", "2026-12-07")
        )

    def test_default_off(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(de.ENABLE_ENV, None)
            self.assertEqual(de.main(["--input", "nonexistent.jsonl"]), 2)

    def test_cli_emits_json(self):
        r = row(
            "c1",
            "CISA Alerts",
            "2026-10-13 12:00:00+00",
            "Ivanti",
            "Version 22.8 reaches end of life on Jan. 31, 2027.",
        )
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "in.jsonl", Path(d) / "out.json"
            src.write_text(json.dumps(r) + "\n", encoding="utf-8")
            code = de.main(
                [
                    "--enable",
                    "--input",
                    str(src),
                    "--as-of",
                    "2027-01-20",
                    "--out",
                    str(out),
                ]
            )
            self.assertEqual(code, 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data[0]["date"], "2027-01-31")
            for k in (
                "event",
                "date",
                "date_basis",
                "source",
                "evidence_span",
                "kind",
                "uncertainty_label",
            ):
                self.assertIn(k, data[0])
            self.assertIn(data[0]["kind"], de.KINDS)
            self.assertIn(data[0]["uncertainty_label"], de.LABELS)


class TestForwardWatchFifthInput(unittest.TestCase):
    def rows(self):
        return [
            row(
                "s1",
                "Supabase Status",
                "2026-11-24 01:56:25+00",
                "Maintenance: Scheduled maintenance: Shared Pooler (Supavisor), eu-west-2",
                "Status: Scheduled (Wed, 09 Dec 2026 13:00:00 GMT - Wed, 09 Dec 2026 15:00:00 GMT) We will perform scheduled maintenance.",
            ),
            row(
                "c1",
                "Cisco Security Advisories",
                "2026-11-13 12:00:00+00",
                "Cisco Advance Notification for Publication of December 2, 2026",
                "On December 2, 2026, Cisco PSIRT will publish advisories for ISE.",
            ),
        ]

    def run_cli(self, extra=(), env=None):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "in.jsonl", Path(d) / "out.md"
            src.write_text(
                "\n".join(json.dumps(r) for r in self.rows()), encoding="utf-8"
            )
            with mock.patch.dict(os.environ, env or {}, clear=False):
                os.environ.pop("INTEL_DATED_EVENTS_ENABLED", None)
                if env:
                    os.environ.update(env)
                fw.main(
                    [
                        "--enable",
                        "--input",
                        str(src),
                        "--as-of",
                        "2026-11-24",
                        "--out",
                        str(out),
                    ]
                    + list(extra)
                )
            return out.read_text(encoding="utf-8")

    def test_default_output_has_no_dated_section_and_matches_render(self):
        text = self.run_cli()
        self.assertNotIn("Dated events", text)
        items, undated, later = fw.extract_items(self.rows(), AS_OF, 42)
        self.assertEqual(
            text,
            fw.render(
                items, undated, later, AS_OF, 42, 2, "events export (read-only SELECT)"
            ),
        )

    def test_flag_adds_section_without_duplicating_listed_items(self):
        text = self.run_cli(["--dated-events"])
        self.assertIn("## Dated events (extractor, flag-gated)", text)
        section = text.split("## Dated events (extractor, flag-gated)")[1].split(
            "## Announced"
        )[0]
        self.assertIn("advisory_deadline", section)
        self.assertIn("2026-12-02", section)
        # the Supabase window is already a primary item; it is not repeated in the new section
        self.assertNotIn("`s1`", section)

    def test_env_flag_also_enables(self):
        text = self.run_cli(env={"INTEL_DATED_EVENTS_ENABLED": "1"})
        self.assertIn("Dated events", text)

    def test_original_sections_unchanged_when_flag_on(self):
        base = self.run_cli()
        flagged = self.run_cli(["--dated-events"])
        for heading in (
            "## Coverage",
            "## Authoritative items by week",
            "## Announced but undated (official sources)",
            "## Relayed by news (not authoritative, not confirmed)",
            "## Limits",
        ):
            self.assertIn(heading, base)
            self.assertIn(heading, flagged)


if __name__ == "__main__":
    unittest.main()
