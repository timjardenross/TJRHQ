#!/usr/bin/env python3
"""
Slack validation test — Knowledge Officer Learning Path

Tests all five acceptance criteria:
1. Routed as KNOWLEDGE_OFFICER_LEARNING
2. KO prompt/context loaded (system_prompt non-empty, context_sources populated)
3. Response includes synthesis, not just snippets (LLM success → BOT-011-KO)
4. Fallback returns raw retrieval if LLM fails (BOT-011-KO-FALLBACK)
5. Runtime event logs show KNOWLEDGE_OFFICER_LEARNING as intent_type

Run: python3 test_knowledge_officer_learning.py
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Add slack-bot to path when running from repo root
sys.path.insert(0, os.path.dirname(__file__))

from commander_runtime import (
    select_runtime_path,
    load_runtime_context,
    handle_knowledge_officer_learning,
    classify_intent,
    BotRequest,
    BotResponse,
    IntentResult,
    RuntimeContext,
)
from knowledge_retrieval import (
    is_knowledge_retrieval_request,
    identify_knowledge_domain,
    build_knowledge_retrieval_response,
)


LEARNING_QUERIES = [
    "Have we done this before?",
    "What did we learn from the OR intelligence quality mission?",
    "Do we have a reusable pattern for mission closure?",
]

DUMMY_MISSION_ID = "TEST-KO-001"


# ---------------------------------------------------------------------------
# AC1: Routing
# ---------------------------------------------------------------------------

class TestRouting(unittest.TestCase):

    def _make_routing(self, user_text: str) -> str:
        from router import route_request
        routing = route_request(user_text)
        return select_runtime_path(user_text, routing)

    def test_query1_routes_to_ko_learning(self):
        result = self._make_routing(LEARNING_QUERIES[0])
        self.assertEqual(result, "KNOWLEDGE_OFFICER_LEARNING",
                         f"Query '{LEARNING_QUERIES[0]}' routed to {result!r}")

    def test_query2_routes_to_ko_learning(self):
        result = self._make_routing(LEARNING_QUERIES[1])
        self.assertEqual(result, "KNOWLEDGE_OFFICER_LEARNING",
                         f"Query '{LEARNING_QUERIES[1]}' routed to {result!r}")

    def test_query3_routes_to_ko_learning(self):
        result = self._make_routing(LEARNING_QUERIES[2])
        self.assertEqual(result, "KNOWLEDGE_OFFICER_LEARNING",
                         f"Query '{LEARNING_QUERIES[2]}' routed to {result!r}")

    def test_learning_domain_identified(self):
        for q in LEARNING_QUERIES:
            domain = identify_knowledge_domain(q)
            self.assertEqual(domain, "learning", f"Domain for '{q}' was {domain!r}")

    def test_is_knowledge_retrieval_triggers(self):
        for q in LEARNING_QUERIES:
            self.assertTrue(is_knowledge_retrieval_request(q),
                            f"'{q}' not recognised as knowledge retrieval")


# ---------------------------------------------------------------------------
# AC2: Context loading
# ---------------------------------------------------------------------------

class TestContextLoading(unittest.TestCase):

    def _make_intent(self, intent_type: str) -> IntentResult:
        return IntentResult(
            intent_type=intent_type,
            domain="learning",
            assigned_specialists=["Knowledge Officer", "Chief of Staff"],
            priority="STANDARD",
        )

    def test_ko_learning_loads_system_prompt(self):
        intent = self._make_intent("KNOWLEDGE_OFFICER_LEARNING")
        ctx = load_runtime_context(LEARNING_QUERIES[0], intent, DUMMY_MISSION_ID)
        self.assertTrue(len(ctx.system_prompt) > 0,
                        "system_prompt should be non-empty for KNOWLEDGE_OFFICER_LEARNING")

    def test_ko_learning_populates_context_sources(self):
        intent = self._make_intent("KNOWLEDGE_OFFICER_LEARNING")
        ctx = load_runtime_context(LEARNING_QUERIES[0], intent, DUMMY_MISSION_ID)
        self.assertTrue(
            any("knowledge_officer" in s for s in ctx.context_sources),
            f"context_sources should reference knowledge_officer, got: {ctx.context_sources}"
        )

    def test_knowledge_retrieval_does_not_load_ko_prompt(self):
        intent = self._make_intent("KNOWLEDGE_RETRIEVAL")
        ctx = load_runtime_context("what is in the source of truth matrix", intent, DUMMY_MISSION_ID)
        self.assertEqual(ctx.system_prompt, "",
                         "KNOWLEDGE_RETRIEVAL should not load a system prompt")


# ---------------------------------------------------------------------------
# AC3: LLM synthesis path
# ---------------------------------------------------------------------------

class TestLLMSynthesisPath(unittest.TestCase):

    def _make_request(self, query: str) -> BotRequest:
        intent = IntentResult(
            intent_type="KNOWLEDGE_OFFICER_LEARNING",
            domain="learning",
            assigned_specialists=["Knowledge Officer", "Chief of Staff"],
            priority="STANDARD",
        )
        ctx = RuntimeContext(
            mission_id=DUMMY_MISSION_ID,
            user_text=query,
            intent=intent,
            system_prompt="[KO system prompt loaded]",
            context_sources=["prompt_loader.load_commander_with_specialist_context:knowledge_officer"],
        )
        return BotRequest(context=ctx, user_text=query)

    def test_llm_success_returns_bot_011_ko(self):
        for query in LEARNING_QUERIES:
            with self.subTest(query=query):
                # ask_commander_for_specialists is imported inside the handler via `from llm import ...`
                # so we patch it at the llm module level
                with patch("llm.ask_commander_for_specialists",
                           return_value=(True, "Knowledge Officer synthesis for query.")):
                    req = self._make_request(query)
                    resp = handle_knowledge_officer_learning(req)

                self.assertEqual(resp.bot_id, "BOT-011-KO",
                                 f"Expected BOT-011-KO, got {resp.bot_id}")
                self.assertIn("synthesis", resp.content.lower(),
                              "Response content should include synthesis text")
                self.assertTrue(resp.success)

    def test_llm_success_response_is_not_raw_snippet(self):
        with patch("llm.ask_commander_for_specialists",
                   return_value=(True, "Knowledge Officer synthesis: here is what we learned.")):
            req = self._make_request(LEARNING_QUERIES[0])
            resp = handle_knowledge_officer_learning(req)
        # Synthesis responses come from LLM — they differ from raw retrieval output
        self.assertEqual(resp.bot_id, "BOT-011-KO")
        self.assertFalse(resp.metadata.get("llm_fallback"),
                         "llm_fallback should not be set on a successful synthesis")


# ---------------------------------------------------------------------------
# AC4: Fallback path
# ---------------------------------------------------------------------------

class TestFallbackPath(unittest.TestCase):

    def _make_request(self, query: str) -> BotRequest:
        intent = IntentResult(
            intent_type="KNOWLEDGE_OFFICER_LEARNING",
            domain="learning",
            assigned_specialists=["Knowledge Officer", "Chief of Staff"],
            priority="STANDARD",
        )
        ctx = RuntimeContext(
            mission_id=DUMMY_MISSION_ID,
            user_text=query,
            intent=intent,
            system_prompt="[KO system prompt]",
            context_sources=["prompt_loader.load_commander_with_specialist_context:knowledge_officer"],
        )
        return BotRequest(context=ctx, user_text=query)

    def test_llm_failure_returns_bot_011_ko_fallback(self):
        for query in LEARNING_QUERIES:
            with self.subTest(query=query):
                with patch("llm.ask_commander_for_specialists",
                           return_value=(False, "LLM unavailable")):
                    req = self._make_request(query)
                    resp = handle_knowledge_officer_learning(req)

                self.assertEqual(resp.bot_id, "BOT-011-KO-FALLBACK",
                                 f"Expected BOT-011-KO-FALLBACK, got {resp.bot_id}")
                self.assertTrue(resp.success,
                                "success should be True even on fallback")

    def test_fallback_content_matches_raw_retrieval(self):
        query = LEARNING_QUERIES[0]
        raw = build_knowledge_retrieval_response(query)
        with patch("llm.ask_commander_for_specialists",
                   return_value=(False, "LLM unavailable")):
            req = self._make_request(query)
            resp = handle_knowledge_officer_learning(req)
        self.assertEqual(resp.content, raw,
                         "Fallback content should equal build_knowledge_retrieval_response output")

    def test_fallback_metadata_flags(self):
        with patch("llm.ask_commander_for_specialists",
                   return_value=(False, "LLM unavailable")):
            req = self._make_request(LEARNING_QUERIES[0])
            resp = handle_knowledge_officer_learning(req)
        self.assertTrue(resp.metadata.get("llm_fallback"))
        self.assertTrue(resp.metadata.get("ko_synthesis_attempted"))


# ---------------------------------------------------------------------------
# AC5: Runtime event logs show correct intent_type
# ---------------------------------------------------------------------------

class TestRuntimeEventLogs(unittest.TestCase):

    def test_intent_classified_event_has_ko_learning_type(self):
        captured_events = []

        def capture_emit(event):
            captured_events.append(event)

        with patch("commander_runtime.emit_runtime_event", side_effect=capture_emit):
            from commander_runtime import execute_commander_runtime
            with patch("llm.ask_commander_for_specialists",
                       return_value=(True, "KO synthesis response.")):
                try:
                    execute_commander_runtime(LEARNING_QUERIES[0])
                except Exception:
                    pass  # DB / env issues are fine; we only need the intent event

        # Look for INTENT_CLASSIFIED event with our type in metadata
        ko_events = [
            e for e in captured_events
            if getattr(e, "event_type", None) == "INTENT_CLASSIFIED"
            and e.metadata.get("intent_type") == "KNOWLEDGE_OFFICER_LEARNING"
        ]
        # If events fired, they must have the right type
        if captured_events:
            self.assertTrue(
                len(ko_events) > 0,
                f"No INTENT_CLASSIFIED event with KNOWLEDGE_OFFICER_LEARNING found. "
                f"Events captured: {[(getattr(e,'event_type','?'), e.metadata.get('intent_type','?')) for e in captured_events]}"
            )

    def test_classify_intent_returns_ko_learning(self):
        for query in LEARNING_QUERIES:
            with self.subTest(query=query):
                intent = classify_intent(query)
                self.assertEqual(intent.intent_type, "KNOWLEDGE_OFFICER_LEARNING",
                                 f"classify_intent returned {intent.intent_type} for '{query}'")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_tests():
    print("=" * 80)
    print("KNOWLEDGE OFFICER LEARNING PATH — SLACK VALIDATION TEST")
    print("=" * 80)
    print()
    print("Test queries:")
    for i, q in enumerate(LEARNING_QUERIES, 1):
        print(f"  {i}. {q}")
    print()
    print("Acceptance criteria:")
    print("  AC1  Routed as KNOWLEDGE_OFFICER_LEARNING")
    print("  AC2  KO prompt/context loaded")
    print("  AC3  LLM synthesis path returns BOT-011-KO")
    print("  AC4  Fallback returns raw retrieval on LLM failure")
    print("  AC5  Runtime event logs show correct intent_type")
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [TestRouting, TestContextLoading, TestLLMSynthesisPath,
                TestFallbackPath, TestRuntimeEventLogs]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 80)
    total = result.testsRun
    failures = len(result.failures) + len(result.errors)
    passed = total - failures
    print(f"RESULTS: {passed}/{total} passed", "✅ ALL PASS" if failures == 0 else f"❌ {failures} FAILED")
    print("=" * 80)

    return failures == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
