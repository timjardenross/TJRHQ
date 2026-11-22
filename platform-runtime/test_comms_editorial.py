"""Tests for the COMMS editorial intelligence uplift (COMMS_EDITORIAL_V2). Pure/offline."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

_BOT = Path(__file__).resolve().parent
if str(_BOT) not in sys.path:
    sys.path.insert(0, str(_BOT))

import commands.comms as comms_cmd
from lib.comms import editorial, pillars, pipeline, portfolio, research_library, weekly
from lib.comms import opportunities as opp
from lib.human_systems import safety

NOW = datetime(2026, 11, 22, tzinfo=timezone.utc)

ROW_S1 = {"id": "p1", "url": "https://notion.example/p1", "name": "National resilience and systemic risk",
          "summary": "Assessment of essential service continuity under cascading disruption and dependency risk.",
          "record_type": "Research Programme", "area": "National & Critical Infrastructure Resilience",
          "status": "Evidence Review", "cut_off": "2026-11-19", "source": "https://regulator.example/report"}
ROW_S2 = {"id": "p2", "url": "https://notion.example/p2", "name": "AI change outpaces assurance capacity",
          "summary": "Technology change, governance and accountability for AI adoption and operational resilience.",
          "record_type": "Research Paper", "area": "Technology & AI", "status": "Active Research",
          "cut_off": "2026-11-22", "source": "https://regulator.example/ai"}
ROW_S3 = {"id": "p3", "url": "https://notion.example/p3", "name": "Economic cost of chronic pain",
          "summary": "Estimates of wellbeing and sustainable performance costs; several figures are proxies.",
          "record_type": "Research Paper", "area": "Health Pain & Neuroscience", "status": "Evidence Review",
          "cut_off": "2026-05-31", "source": None}


def _scored(rows, extra=None, existing=(), signals=None):
    items = opp.library_opportunities(rows) + list(extra or [])
    return opp.apply_editorial(items, existing_titles=list(existing), signals=signals, now=NOW)


class TestStreamsAndScoring(unittest.TestCase):
    def test_weights_sum_to_100(self):
        self.assertEqual(sum(editorial.WEIGHTS.values()), 100)
        self.assertEqual(editorial.WEIGHTS, {"audience": 30, "alignment": 25, "evidence": 20,
                                             "originality": 15, "timeliness": 10})

    def test_every_streamed_pillar_exists_and_unstreamed_are_excluded(self):
        for k in editorial.PILLAR_STREAM:
            self.assertIn(k, pillars.PILLARS_BY_KEY)
        self.assertNotIn("personal_operating_systems", editorial.PILLAR_STREAM)
        self.assertNotIn("future_of_work", editorial.PILLAR_STREAM)

    def test_word_boundary_not_substring(self):
        stream, _p, hits = editorial.classify_stream("The team said we maintain history")
        self.assertIsNone(stream)
        self.assertEqual(hits, 0)

    def test_score_parts_sum_and_bounds(self):
        items = _scored([ROW_S1])
        sc = items[0].escore
        self.assertEqual(sc.total, sc.audience + sc.alignment + sc.evidence + sc.originality + sc.timeliness)
        self.assertLessEqual(sc.audience, 30)
        self.assertLessEqual(sc.evidence, 20)

    def test_internal_implementation_scores_lower_on_audience(self):
        internal = opp.build_opportunity("mission", ref="M1", title="Resilience pipeline for the Endeavour",
            body="mission scheduler pipeline migration resilience continuity officer bot")
        clean = opp.build_opportunity("mission", ref="M2", title="Resilience dependency lessons",
            body="resilience continuity disruption dependency lessons for leaders")
        a = _scored([], [internal, clean])
        by = {o.source_ref: o.escore for o in a}
        self.assertLess(by["M1"].audience, by["M2"].audience)

    def test_stale_evidence_flagged(self):
        sc = _scored([ROW_S3])[0].escore
        self.assertIn("evidence cut-off is older than 90 days", sc.gaps)

    def test_library_rows_never_labelled_fact(self):
        o = _scored([ROW_S1])[0]
        o.info.claim_type = "F"
        self.assertEqual(editorial.claim_label(o.info), "[A]")


class TestSelection(unittest.TestCase):
    def test_threshold_and_evidence_floor(self):
        self.assertEqual(editorial.MIN_TOTAL, 65)
        self.assertEqual(editorial.MIN_EVIDENCE, 8)
        weak = editorial.EditorialScore(editorial.S3, 20, 20, 5, 10, 8, 63, "Needs research", [], False, [])
        self.assertFalse(weak.eligible)
        high_total_low_evidence = editorial.EditorialScore(editorial.S1, 30, 25, 7, 15, 10, 87, "x", [], False, [])
        self.assertFalse(high_total_low_evidence.eligible)

    def test_weak_stream_gets_no_recommendation(self):
        items = _scored([ROW_S1, ROW_S2, ROW_S3])
        scored = [(i, o, o.escore) for i, o in enumerate(items, 1)]
        picks = editorial.select_per_stream(scored)
        self.assertIsNone(picks[editorial.S3])

    def test_duplicates_removed(self):
        items = _scored([ROW_S1], existing=["National resilience and systemic risk"])
        self.assertEqual(items, [])
        items = _scored([ROW_S1], existing=["Completely different topic about sleep"])
        self.assertEqual(len(items), 1)

    def test_shared_theme_only_when_overlap(self):
        self.assertTrue(editorial.shared_theme("assurance capacity change resilience",
                                               "change outpaces assurance resilience"))
        self.assertEqual(editorial.shared_theme("sleep recovery", "central bank policy"), [])


class TestGovernance(unittest.TestCase):
    def test_screen_blocks_architecture_and_hosts(self):
        self.assertIn("supabase", editorial.screen("we store rows in Supabase"))
        self.assertIn("hostname/ip", editorial.screen("reach 10.0.0.12 for the box"))
        self.assertEqual(editorial.screen("systemic risk in essential services"), [])

    def test_employer_terms_configurable(self):
        with patch.dict(os.environ, {"COMMS_CONFIDENTIAL_TERMS": "acmecorp"}):
            self.assertIn("acmecorp", editorial.screen("lessons at AcmeCorp"))

    def test_blocked_item_demoted_and_never_recommended(self):
        o = opp.build_opportunity("lesson", ref="L1", title="Resilience lessons",
                                  body="continuity and recovery via our supabase telegram pipeline")
        out = _scored([], [o])
        self.assertEqual(out[0].classification, opp.INTERNAL_ONLY)
        self.assertFalse(out[0].escore.eligible)

    def test_brief_withholds_internal_detail_and_passes_language_check(self):
        row = dict(ROW_S1, summary="Resilience dependency continuity on supabase and systemd hosts.")
        items = _scored([row, ROW_S2])
        with patch.dict(os.environ, {editorial.FLAG: "1"}):
            out = weekly.compose_weekly_brief(items, date_str="x")
        self.assertNotIn("supabase", out.lower())
        self.assertEqual(safety.check_language(out), [])
        self.assertIn("Nothing is published without Captain approval", out)

    def test_pipeline_captain_gates_unchanged(self):
        self.assertIn("captain_approved", pipeline.CAPTAIN_ONLY_TRIGGERS)
        self.assertIn("captain_confirmed", pipeline.CAPTAIN_ONLY_TRIGGERS)
        self.assertIsNone(pipeline.advance("x", "captain_approved", "communications"))

    def test_no_outbound_publishing_in_editorial_modules(self):
        for mod in (editorial, research_library):
            src = Path(mod.__file__).read_text().lower()
            for banned in ("linkedin.com", "api.twitter", "ugcposts", "sendmessage"):
                self.assertNotIn(banned, src)
        self.assertNotIn("post", [m for m in dir(research_library) if m == "post"])


class TestBriefOutput(unittest.TestCase):
    def _brief(self, rows, **kw):
        items = _scored(rows, **kw)
        with patch.dict(os.environ, {editorial.FLAG: "1"}):
            return items, weekly.compose_weekly_brief(items, date_str="Sun 22 Nov 2026")

    def test_required_fields_present(self):
        _items, out = self._brief([ROW_S1, ROW_S2, ROW_S3])
        for needle in ("Target audience", "Why now", "Central argument", "Evidence and sources",
                       "Format", "Score:", "Remaining gaps", "/100", "No recommendation this week",
                       "Captain"):
            self.assertIn(needle, out)

    def test_draft_index_matches_list_position(self):
        items, out = self._brief([ROW_S1, ROW_S2])
        import re
        for idx in map(int, re.findall(r"/comms draft (\d+)", out)):
            self.assertTrue(1 <= idx <= len(items))
            self.assertIn(items[idx - 1].title, out)

    def test_flag_off_keeps_legacy_brief(self):
        o = opp.build_opportunity("mission", ref="R1", title="Operational shakedown",
                                  body="incident recovery continuity")
        with patch.dict(os.environ, {editorial.FLAG: ""}):
            out = weekly.compose_weekly_brief([o])
        self.assertIn("What should I be talking about this week", out)
        self.assertIn("Strategic alignment", out)

    def test_empty_degrades(self):
        with patch.dict(os.environ, {editorial.FLAG: "1"}):
            out = weekly.compose_weekly_brief([])
        self.assertIn("No publishable opportunities", out)


class TestOrderingContractAndOffline(unittest.TestCase):
    def test_weekly_and_draft_use_same_ranked_list(self):
        items = _scored([ROW_S1, ROW_S2])
        with (
            patch.object(opp, "gather_opportunities", return_value=items),
            patch.dict(os.environ, {editorial.FLAG: "1"}),
            patch.object(comms_cmd.drafting, "generate_draft", return_value=("scaffold", "BODY")) as g,
            patch.object(comms_cmd.portfolio, "record_content", return_value=True) as rec,
        ):
            out = comms_cmd._weekly()
            comms_cmd._draft("1")
        self.assertIn(items[0].title, out)
        self.assertEqual(g.call_args[0][0].title, items[0].title)
        self.assertIn("editorial=", rec.call_args.kwargs["notes"])

    def test_sensitive_draft_still_requires_confirm(self):
        items = _scored([ROW_S1])
        items[0].content_classification = "personal_story"
        with patch.object(opp, "gather_opportunities", return_value=items), \
             patch.object(comms_cmd, "requires_approval", return_value=True):
            self.assertIn("Captain approval required", comms_cmd._draft("1"))

    def test_offline_flag_on_yields_empty(self):
        with patch.dict(os.environ, {editorial.FLAG: "1"}), \
             patch.object(opp, "_client", return_value=None), \
             patch.object(opp, "_gather_outcome_candidates", return_value=[]), \
             patch.object(opp, "_gather_library", return_value=[]), \
             patch.object(opp, "_existing_titles", return_value=[]), \
             patch.object(opp, "_gather_signals", return_value=[]):
            self.assertEqual(opp.gather_opportunities(), [])

    def test_library_adapter_graceful_and_parses(self):
        with patch.dict(os.environ, {"NOTION_TOKEN": ""}):
            self.assertEqual(research_library.fetch_rows(), [])
        payload = {"results": [{"id": "1", "url": "u", "properties": {
            "Name": {"type": "title", "title": [{"plain_text": "T"}]},
            "Summary": {"type": "rich_text", "rich_text": [{"plain_text": "S"}]},
            "Research Area": {"type": "select", "select": {"name": "Technology & AI"}},
            "Status": {"type": "select", "select": {"name": "Active Research"}},
            "Evidence Cut-off": {"type": "date", "date": {"start": "2026-11-22"}}}}]}
        rows = research_library.fetch_rows(http=lambda ds, n: payload)
        self.assertEqual(rows[0]["name"], "T")
        self.assertEqual(rows[0]["cut_off"], "2026-11-22")

    def test_signals_add_corroboration_and_timeliness(self):
        sig = [{"event_id_text": "e1", "source_name": "Regulator",
                "suggested_angle": "essential service continuity cascading disruption",
                "scored_at": "2026-11-21T00:00:00Z"}]
        base = _scored([dict(ROW_S1, source=None, cut_off=None)])[0].escore
        withsig = _scored([dict(ROW_S1, source=None, cut_off=None)], signals=sig)[0]
        self.assertGreater(withsig.escore.total, base.total)
        self.assertTrue(any("signal:e1" in r for r in withsig.info.external_refs))

    def test_record_content_idempotent_and_no_downgrade(self):
        class Tbl:
            def __init__(s, row): s.row, s.ops = row, []
            def select(s, *a): return s
            def eq(s, *a): return s
            def limit(s, *a): return s
            def update(s, p): s.ops.append(("update", p)); return s
            def execute(s):
                class R: pass
                r = R(); r.data = [s.row] if s.row else []; return r
        class C:
            def __init__(s, row): s.t = Tbl(row); s.raw_client = s
            def table(s, n): return s.t
            def insert(s, *a, **k): raise AssertionError("must not insert when row exists")
        with patch.dict(os.environ, {editorial.FLAG: "1"}):
            adv = C({"id": "u1", "status": "published"})
            with patch.object(portfolio, "_client", return_value=adv):
                self.assertTrue(portfolio.record_content(content_id="c", title="t", status="draft"))
            self.assertEqual(adv.t.ops, [])          # published is never downgraded
            drf = C({"id": "u2", "status": "draft"})
            with patch.object(portfolio, "_client", return_value=drf):
                self.assertTrue(portfolio.record_content(content_id="c", title="t", status="draft"))
            self.assertEqual(len(drf.t.ops), 1)       # updated in place, not duplicated


if __name__ == "__main__":
    unittest.main()


# ── Captain-approved evidence-scoring corrections ─────────────────────────────

def _info(kind_names, status="Evidence Review", as_of="2026-11-22"):
    """EditorialInfo with graded external sources from (source_name) list."""
    info = editorial.EditorialInfo(stream=editorial.S1, evidence_grade="unverified_library",
                                   research_status=status, as_of=as_of)
    for n, name in enumerate(kind_names):
        info.external_refs.append(f"signal:{n} ({name})")
        info.external_sources.append({"ref": str(n), "kind": editorial.grade_signal_source(name),
                                      "family": name.lower()})
    return info


def _score(info):
    return editorial.score_candidate("Essential services dependency risk", "resilience continuity cascading disruption",
                                     info, source_kind="library", now=NOW)


class TestEvidenceCorrections(unittest.TestCase):
    def test_news_only_corroboration_is_capped(self):
        sc = _score(_info(["Bloomberg", "ABC News", "Guardian Australia", "BBC News"]))
        self.assertLessEqual(sc.evidence, editorial.NEWS_ONLY_EVIDENCE_CAP)
        self.assertFalse(sc.evidence >= editorial.READY_EVIDENCE)

    def test_repeated_headlines_from_one_publisher_count_once(self):
        one = _score(_info(["Bloomberg"])).evidence
        many = _score(_info(["Bloomberg"] * 5)).evidence
        self.assertEqual(one, many)

    def test_aggregator_adds_little_and_commentary_nothing(self):
        base = _score(_info([])).evidence
        agg = _score(_info(["Google News - Critical Infrastructure"])).evidence
        content = _score(_info(["Inc. Magazine — Leadership"])).evidence
        self.assertLessEqual(agg - base, 1)
        self.assertEqual(content, base)

    def test_strong_evidence_needs_a_primary_source_and_two_publishers(self):
        one_family = _score(_info(["CISA Alerts"])).evidence
        two_families = _score(_info(["CISA Alerts", "Bloomberg"])).evidence
        self.assertLessEqual(one_family, editorial.READY_EVIDENCE - 1)
        self.assertGreater(two_families, one_family)

    def test_aggregator_about_a_regulator_is_not_primary(self):
        self.assertEqual(editorial.grade_signal_source("Google News - APRA/ASIC Operational Resilience"), "aggregator")
        self.assertEqual(editorial.grade_signal_source("APRA Media Releases"), "primary")

    def test_evidence_is_an_integer(self):
        self.assertIsInstance(_score(_info(["Bloomberg", "CISA Alerts"])).evidence, int)

    def test_unverified_library_row_never_reaches_ready_on_news_alone(self):
        sc = _score(_info(["Bloomberg", "ABC News", "BBC News", "Guardian Australia", "Financial Times"]))
        self.assertNotEqual(sc.readiness, "Ready for drafting")


class TestSignalMatchingCorrections(unittest.TestCase):
    def _opp(self):
        o = opp.library_opportunities([ROW_S1])[0]
        return o

    def test_two_shared_terms_no_longer_match(self):
        o = self._opp()
        sig = {"event_id_text": "e", "source_name": "Bloomberg",
               "suggested_angle": "essential services opinion", "scored_at": "2026-11-21T00:00:00Z"}
        self.assertFalse(opp._signal_matches(o, sig))

    def test_three_shared_terms_match(self):
        o = self._opp()
        sig = {"event_id_text": "e", "source_name": "Bloomberg",
               "suggested_angle": "essential service continuity cascading disruption",
               "scored_at": "2026-11-21T00:00:00Z"}
        self.assertTrue(opp._signal_matches(o, sig))

    def test_signal_from_a_different_stream_is_rejected(self):
        o = self._opp()                               # resilience stream
        sig = {"event_id_text": "e", "source_name": "Bloomberg", "pillar_key": "human_performance",
               "suggested_angle": "essential service continuity cascading disruption"}
        self.assertFalse(opp._signal_matches(o, sig))

    def test_attached_signals_record_kind_and_family(self):
        o = self._opp()
        opp.attach_signals([o], [{"event_id_text": "e1", "source_name": "Google News - Telstra",
                                  "suggested_angle": "essential service continuity cascading disruption",
                                  "scored_at": "2026-11-21T00:00:00Z"}])
        self.assertEqual(o.info.external_sources[0]["kind"], "aggregator")


class TestCrossPRCompatibility(unittest.TestCase):
    NAMES = ("CISA Alerts", "Google News - APRA/ASIC Operational Resilience", "APRA Media Releases", "Bloomberg",
             "ABC News", "iTnews", "Inc. Magazine — Leadership", "Cisco Security Advisories", "AEMO Market Notices",
             "ClinicalTrials.gov", "Google News - Telstra", "Some Unknown Blog")

    def test_source_grading_agrees_with_weekly_evidence_when_both_present(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        try:
            import intelligence.weekly_evidence as we
        except ImportError:
            self.skipTest("intelligence.weekly_evidence not present (PR #660 not merged)")
        for n in self.NAMES:
            theirs = we.source_kind(n)
            mine = editorial.grade_signal_source(n)
            if theirs == "registry":          # #658 has no registry kind (it never receives registry rows)
                continue
            self.assertEqual(mine, theirs, n)
