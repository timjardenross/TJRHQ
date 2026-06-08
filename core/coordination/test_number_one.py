#!/usr/bin/env python3
"""
Test Suite for Number One Coordination Layer

Tests all 6 core capabilities:
  1. Work queue generation
  2. Follow-up detection
  3. Blocker management
  4. Specialist coordination
  5. Daily coordination brief
  6. XO escalation engine

Run: python3 test_number_one.py
"""

import sys
from datetime import datetime, timedelta
from number_one import (
    NumberOne,
    Mission,
    MissionStatus,
    Priority,
    ConfidenceBand,
    RoutingDecision,
    EscalationLevel,
    CoordinationConfig,
)


# ============================================================================
# Test Fixtures
# ============================================================================

def create_test_mission(
    mission_id: str,
    priority: Priority = Priority.P1,
    status: MissionStatus = MissionStatus.ACTIVE,
    blockers: list = None,
    last_updated: datetime = None,
    assigned_role: str = None,
) -> dict:
    """Create a test mission dict."""
    now = datetime.utcnow()
    if last_updated is None:
        last_updated = now

    return {
        "mission_id": mission_id,
        "title": f"Mission {mission_id}",
        "status": status.value,
        "priority": priority.value,
        "domain": "engineering",
        "assigned_role": assigned_role,
        "assigned_specialists": [assigned_role] if assigned_role else [],
        "dependencies": [],
        "blockers": blockers or [],
        "created_at": (now - timedelta(days=10)).isoformat() + "Z",
        "last_updated": last_updated.isoformat() + "Z",
        "next_action": None,
        "metadata": {},
    }


def create_routing_decision(
    primary: str = "Chief Engineer",
    confidence: float = 0.91,
    intent: str = "architecture_review",
) -> RoutingDecision:
    """Create a test routing decision."""
    return RoutingDecision(
        primary_specialist=primary,
        secondary_specialists=[],
        intent=intent,
        confidence=confidence,
        confidence_band=(
            ConfidenceBand.HIGH if confidence >= 0.80
            else ConfidenceBand.MEDIUM if confidence >= 0.55
            else ConfidenceBand.LOW
        ),
        rationale=f"Test routing for {primary}",
    )


# ============================================================================
# Test Cases
# ============================================================================

class TestNumberOne:
    """Test suite for Number One."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.config = CoordinationConfig()
        self.number_one = NumberOne(self.config)

    def run_all_tests(self):
        """Run all tests."""
        print("=" * 80)
        print("NUMBER ONE COORDINATION LAYER — TEST SUITE")
        print("=" * 80)
        print()

        self.test_work_queue_generation()
        self.test_follow_up_detection()
        self.test_blocker_management()
        self.test_specialist_coordination()
        self.test_daily_brief_generation()
        self.test_xo_escalations()

        print()
        print("=" * 80)
        print(f"RESULTS: {self.passed} passed, {self.failed} failed")
        print("=" * 80)
        print()

        return self.failed == 0

    def test_work_queue_generation(self):
        """Test 1: Work queue generation and sorting."""
        print("TEST 1: Work Queue Generation")
        print("-" * 80)

        missions = [
            create_test_mission("MSN-0030", Priority.P1, MissionStatus.ACTIVE),
            create_test_mission("MSN-0031", Priority.P2, MissionStatus.PROPOSED),
            create_test_mission("MSN-0032", Priority.P0, MissionStatus.ACTIVE),
        ]

        queue = self.number_one.get_work_queue(missions)

        # Check 1: Queue is sorted by priority (P0 before P1, P1 before P2)
        self.assert_true(
            queue[0].priority == Priority.P0,
            "First item should be P0 (MSN-0032)"
        )
        self.assert_true(
            queue[1].priority == Priority.P1,
            "Second item should be P1 (MSN-0030)"
        )
        self.assert_true(
            queue[2].priority == Priority.P2,
            "Third item should be P2 (MSN-0031)"
        )

        # Check 2: ACTIVE missions appear before PROPOSED within same priority
        missions2 = [
            create_test_mission("MSN-A", Priority.P1, MissionStatus.PROPOSED),
            create_test_mission("MSN-B", Priority.P1, MissionStatus.ACTIVE),
        ]
        queue2 = self.number_one.get_work_queue(missions2)
        self.assert_true(
            queue2[0].mission_id == "MSN-B",
            "ACTIVE should appear before PROPOSED"
        )

        # Check 3: Blockers shown in queue items
        missions3 = [create_test_mission("MSN-BLOCK", blockers=["Waiting for review"])]
        queue3 = self.number_one.get_work_queue(missions3)
        self.assert_true(
            len(queue3[0].blockers) > 0,
            "Queue item should show blockers"
        )

        print()

    def test_follow_up_detection(self):
        """Test 2: Follow-up detection (stale, blocked, missing)."""
        print("TEST 2: Follow-Up Detection")
        print("-" * 80)

        # Create missions with various follow-up triggers
        now = datetime.utcnow()
        stale_date = now - timedelta(days=6)  # 6 days old
        recent_date = now - timedelta(days=1)  # 1 day old

        missions = [
            create_test_mission("MSN-STALE", last_updated=stale_date),
            create_test_mission("MSN-RECENT", last_updated=recent_date),
            create_test_mission("MSN-NO-SPEC", assigned_role=None, status=MissionStatus.ACTIVE),
            create_test_mission("MSN-BLOCKED", status=MissionStatus.BLOCKED, blockers=["Pending review"]),
        ]

        follow_ups = self.number_one.get_follow_ups(missions)

        # Check 1: Stale missions detected
        stale_follow_ups = [f for f in follow_ups if f["type"] == "STALE_MISSION"]
        self.assert_true(
            len(stale_follow_ups) > 0,
            "Should detect stale missions"
        )

        # Check 2: Missing specialist detected
        missing_spec = [f for f in follow_ups if f["type"] == "MISSING_SPECIALIST"]
        self.assert_true(
            any(f["mission_id"] == "MSN-NO-SPEC" for f in missing_spec),
            "Should detect missing specialist on ACTIVE mission"
        )

        # Check 3: Each follow-up has recommendation
        self.assert_true(
            all("recommendation" in f for f in follow_ups),
            "All follow-ups should have recommendations"
        )

        print()

    def test_blocker_management(self):
        """Test 3: Blocker management and reporting."""
        print("TEST 3: Blocker Management")
        print("-" * 80)

        missions = [
            create_test_mission("P0-BLOCKED", Priority.P0, MissionStatus.BLOCKED, ["Critical issue"]),
            create_test_mission("P1-BLOCKED", Priority.P1, MissionStatus.BLOCKED, ["Minor issue"]),
            create_test_mission("ACTIVE", Priority.P1, MissionStatus.ACTIVE),
        ]

        blockers = self.number_one.get_blockers(missions)

        # Check 1: Blockers categorized by severity
        self.assert_true(
            len(blockers["critical"]) > 0,
            "Should have critical blockers"
        )
        self.assert_true(
            len(blockers["high"]) > 0,
            "Should have high blockers"
        )

        # Check 2: Total blocker count correct
        total = len(blockers["critical"]) + len(blockers["high"]) + len(blockers["normal"])
        self.assert_true(
            total == blockers["total_blockers"],
            "Blocker count should match sum of categories"
        )

        # Check 3: Active missions not in blocker report
        active_in_blockers = any(
            b["mission_id"] == "ACTIVE"
            for block_list in [blockers["critical"], blockers["high"], blockers["normal"]]
            for b in block_list
        )
        self.assert_false(
            active_in_blockers,
            "Active missions should not be in blocker report"
        )

        print()

    def test_specialist_coordination(self):
        """Test 4: Specialist coordination with routing."""
        print("TEST 4: Specialist Coordination")
        print("-" * 80)

        missions = [
            create_test_mission("MSN-1"),
            create_test_mission("MSN-2"),
            create_test_mission("MSN-3"),
        ]

        routing = {
            "MSN-1": create_routing_decision("Chief Engineer", confidence=0.91),  # HIGH
            "MSN-2": create_routing_decision("Coder Agent", confidence=0.67),  # MEDIUM
            "MSN-3": create_routing_decision("Risk Officer", confidence=0.48),  # LOW
        }

        queue = self.number_one.get_work_queue(missions, routing)

        # Check 1: High confidence specialist shown confidently
        high_conf = [q for q in queue if q.mission_id == "MSN-1"][0]
        self.assert_true(
            high_conf.confidence_band == ConfidenceBand.HIGH,
            "High confidence routing should be HIGH band"
        )

        # Check 2: Low confidence specialist escalated
        low_conf = [q for q in queue if q.mission_id == "MSN-3"][0]
        self.assert_true(
            "XO" in (low_conf.assigned_specialist or ""),
            "Low confidence should escalate to XO"
        )

        # Check 3: Confidence values preserved
        self.assert_true(
            high_conf.confidence == 0.91,
            "Confidence value should be preserved"
        )

        print()

    def test_daily_brief_generation(self):
        """Test 5: Daily coordination brief."""
        print("TEST 5: Daily Brief Generation")
        print("-" * 80)

        now = datetime.utcnow()
        missions = [
            create_test_mission("P0-A", Priority.P0, MissionStatus.ACTIVE),
            create_test_mission("P1-B", Priority.P1, MissionStatus.ACTIVE),
            create_test_mission("P1-C", Priority.P1, MissionStatus.BLOCKED),
            create_test_mission("P2-D", Priority.P2, MissionStatus.PROPOSED),
            create_test_mission("STALE", last_updated=now - timedelta(days=6)),
        ]

        brief = self.number_one.get_daily_brief(missions)

        # Check 1: Metrics accurate
        self.assert_true(
            brief.total_missions == 5,
            "Total mission count correct"
        )
        self.assert_true(
            brief.active_count == 3,
            "Active count correct (P0-A, P1-B, STALE)"
        )
        self.assert_true(
            brief.blocked_count == 1,
            "Blocked count correct"
        )

        # Check 2: Top priorities included
        self.assert_true(
            len(brief.top_priorities) > 0,
            "Brief should have top priorities"
        )

        # Check 3: System health set
        self.assert_true(
            brief.system_health in ["green", "yellow", "red"],
            "System health should be set"
        )

        # Check 4: Recommended actions generated
        self.assert_true(
            len(brief.recommended_actions) > 0,
            "Brief should have recommended actions"
        )

        print()

    def test_xo_escalations(self):
        """Test 6: XO escalation detection."""
        print("TEST 6: XO Escalation Engine")
        print("-" * 80)

        now = datetime.utcnow()
        missions = [
            # Critical: Blocked P0
            create_test_mission("P0-BLOCKED", Priority.P0, MissionStatus.BLOCKED),
            # High: Extended block on P1
            create_test_mission("P1-LONG-BLOCKED", Priority.P1, MissionStatus.BLOCKED, last_updated=now - timedelta(days=4)),
            # High: Stale P0
            create_test_mission("P0-STALE", Priority.P0, last_updated=now - timedelta(days=3)),
            # Medium: Low confidence
            create_test_mission("LOW-CONF"),
            # Normal: Recent active mission
            create_test_mission("NORMAL", Priority.P1, MissionStatus.ACTIVE, last_updated=now - timedelta(days=1)),
        ]

        routing = {
            "LOW-CONF": create_routing_decision("Chief Engineer", confidence=0.48),  # LOW
        }

        escalations = self.number_one.get_xo_escalations(missions, routing)

        # Check 1: Critical escalations present
        critical = [e for e in escalations if e.level == EscalationLevel.CRITICAL]
        self.assert_true(
            len(critical) > 0,
            "Should have critical escalations"
        )

        # Check 2: High escalations present
        high = [e for e in escalations if e.level == EscalationLevel.HIGH]
        self.assert_true(
            len(high) > 0,
            "Should have high escalations"
        )

        # Check 3: Escalations sorted by level (CRITICAL before HIGH before MEDIUM)
        level_values = [
            {
                EscalationLevel.CRITICAL: 0,
                EscalationLevel.HIGH: 1,
                EscalationLevel.MEDIUM: 2,
            }[e.level]
            for e in escalations
        ]
        self.assert_true(
            level_values == sorted(level_values),
            "Escalations should be sorted by level (CRITICAL, HIGH, MEDIUM)"
        )

        # Check 4: Each escalation has recommendation
        self.assert_true(
            all(e.recommendation for e in escalations),
            "All escalations should have recommendations"
        )

        print()

    # ========================================================================
    # Assertion Helpers
    # ========================================================================

    def assert_true(self, condition: bool, message: str):
        """Assert condition is true."""
        if condition:
            print(f"  ✅ {message}")
            self.passed += 1
        else:
            print(f"  ❌ {message}")
            self.failed += 1

    def assert_false(self, condition: bool, message: str):
        """Assert condition is false."""
        self.assert_true(not condition, message)


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    tester = TestNumberOne()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
