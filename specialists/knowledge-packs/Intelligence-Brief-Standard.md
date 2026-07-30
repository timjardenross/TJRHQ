# Intelligence Brief Standard — USS TJR Operational Resilience

## Overview

An Intelligence Brief (ResilienceBrief) is the primary operational intelligence artifact for the Captain. It synthesizes 14+ days of operational signals, emerging threats, and forward-watching indicators into a single executive decision document.

This standard defines the required fields, quality thresholds, and review process for all briefs before publication.

---

## Required Fields

Every brief MUST contain all six core fields below. Absence of any field is grounds for rejection during the QA pre-screen.

### 1. Executive Snapshot

**Purpose:** The first 2-3 sentences the Captain will read.

**Criteria:**
- Captures the single most important operational finding from the review period
- Written in plain English (no acronyms without explanation)
- Actionable — tells the Captain what they need to pay attention to
- Maximum 200 words; prefer 100

**Example:**
> Three critical infrastructure services showed degradation across three regions this week. AWS and Azure experienced routing delays affecting 15% of our connected systems. The pattern suggests a shared backbone issue, not isolated incidents.

**Auto-checked by:** Brief QA pre-screen (snapshot_reflects_events, 30% weight)

---

### 2. Emerging Themes

**Purpose:** Answer "what patterns are emerging from the noise?"

**Criteria:**
- Distinct from individual events — clusters them into themes
- Grounded in the top_events dataset (tied to evidence)
- Predictive rather than purely historical
- 150 words typical

**Example:**
> Authentication failures increased 8% week-over-week across three unrelated systems, all converging on expired TLS certificates. This suggests either: (a) a coordinated cert-renewal failure, or (b) a scanning/probing campaign testing certificate infrastructure.

**Auto-checked by:** Brief QA pre-screen (themes_grounded_in_data, 30% weight)

---

### 3. Forward Watch

**Purpose:** "What should we monitor next?"

**Criteria:**
- Derived from emerging themes and external intelligence
- Specific (not vague warnings like "watch for cyber threats")
- Measurable or observable
- Focuses on the next 14 days

**Example:**
> Watch certificate renewal schedules for the three affected systems. Monitor their dashboards for ANY spike in authentication rejections >5% in the next 48h. Check with AWS/Azure support whether they have coordinated maintenance windows scheduled.

**Auto-checked by:** Brief QA pre-screen (forward_watch_justified, 30% weight)

---

### 4. CPS 230 Implications

**Purpose:** Operational Resilience Act compliance context.

**Criteria:**
- Explicitly ties findings to APRA CPS 230 critical operations or operational resilience
- Explains impact on scenario testing requirements
- Grounded in the CPS230 impact ratings on top_events
- Can reference "no direct CPS 230 impact this period" if accurate

**Example:**
> The authentication failures, if sustained, would impact our access to payment processing systems (Core 1 criticality, RTO: 4h). This aligns with CPS 230 Scenario A (cyber-enabled service disruption). Current mitigation: automated cert-renewal in place; recommend validating automation with a dry-run this quarter.

**Auto-checked by:** Brief QA pre-screen (cps230_anchored_to_domain, 30% weight)

---

### 5. Bottom Line

**Purpose:** What is the Captain deciding/doing with this brief?

**Criteria:**
- Recommends one specific next action (or explicitly "monitor, do not act")
- Owner/timeline clear
- Ties to the risk_rating (RED → act immediately; AMBER → schedule this week; GREEN → monitor)
- Maximum 100 words

**Example:**
> **Action:** Conduct a cert-renewal dry-run for the three affected services within 48 hours. Coordinate with Cloud Ops to validate automation before expiration windows arrive. If any test fails, escalate to VP Infrastructure immediately.

**Auto-checked by:** Brief QA pre-screen (completeness, 25% weight)

---

### 6. Overall Risk Rating

**Purpose:** One-word severity scale for quick scanning and alerting.

**Options:**
- **RED** — Immediate action required; escalate to Captain immediately; triggers automated Telegram escalation
- **AMBER** — Action needed within one business day; schedule for review
- **GREEN** — Monitor; no immediate action; routine observation
- **UNKNOWN** — Insufficient data to rate; gather more intelligence before next cycle

**Rules:**
- RED briefs ALWAYS receive human review, regardless of QA score
- Cannot be assigned by the automated pre-screen if any top_event contradicts it
- Justified by: highest risk_rating in top_events + confidence in evidence

**Auto-checked by:** Brief QA pre-screen (risk_accuracy, 25% weight)

---

## Quality Thresholds

### Automated Pre-Screen (runs nightly at 02:00 AEST)

Every brief in IN_REVIEW status is scored on five dimensions:

| Dimension | Weight | Threshold | Notes |
|-----------|--------|-----------|-------|
| Completeness | 25% | All 6 fields present, non-empty | Missing even one field = auto-fail |
| Coherence | 30% | Snapshot, themes, forward_watch grounded in top_events | Checks cross-reference with signal data |
| Risk Accuracy | 25% | overall_risk justified by top_event ratings | Must not underrate highest event in the brief |
| Freshness | 20% | Generated ≤7 days ago | Stale briefs (>7 days in review) score lower |
| **Passing Score** | **100** | **≥85** | Failing briefs routed to human review |

### Human Review (required for all RED briefs, all failures)

The Intelligence Lead reviews failures and RED-rated briefs. Human review is the final gate; the automated score is advisory only.

**Human QA checklist:**
- [ ] Does the narrative match the data, or is the Captain being misled?
- [ ] Are the implications realistic given the CPS 230 context?
- [ ] Is the recommended action clear and resourced?
- [ ] Is the risk rating defensible (not alarmist, not under-stated)?
- [ ] Would you stake your reputation on this brief being published?

---

## Review Workflow

```
Brief generated (in-band via BriefGenerator)
          ↓
Brief stored in IN_REVIEW status
          ↓
[Nightly at 02:00] Automated pre-screen runs
          ↓
If score ≥85 AND not RED
  → Auto-advance to QA_PASSED
Else (RED OR score <85)
  → Remain in IN_REVIEW for human review
          ↓
Intelligence Lead reviews & calls qa_pass() with actor='intelligence_lead'
          ↓
Brief moves to QA_PASSED → Published
```

---

## Examples

### ✅ PASSING Brief (Score: 88)

**Executive Snapshot:**
Telstra's network routing experienced a 3-hour outage affecting 12% of connected downstream systems on 2026-07-24 afternoon. Cause: undersized BGP buffer on one edge router. No cascading failures.

**Emerging Themes:**
Second time in four weeks that Telstra's infrastructure has hit hidden scaling limits under normal load. Pattern suggests under-provisioning rather than one-off failure.

**Forward Watch:**
1. Request Telstra capacity plan for next quarter — are they planning upgrades?
2. Model impact if Telstra were offline 24h (scenario testing input)
3. Check whether our own BGP redundancy could have masked this from downstream

**CPS 230 Implications:**
Telstra is a primary source for network connectivity (Operational Resilience Standard 1, RTO: 8h). This outage tested our redundancy; it held. Recommend documenting the mitigation as evidence of CPS 230 scenario readiness.

**Bottom Line:**
No action required immediately. Use this incident as a data point in this year's CPS 230 scenario report: "External provider infrastructure can fail at scale."

**Overall Risk:** GREEN (managed by existing redundancy)

---

### ❌ FAILING Brief (Score: 42 — Red-rated)

**Executive Snapshot:**
[MISSING]

**Emerging Themes:**
General cyber threat landscape is increasing.

**Forward Watch:**
Monitor the internet.

**CPS 230 Implications:**
This could affect operations.

**Bottom Line:**
[MISSING]

**Overall Risk:** RED

**Failure reasons:**
1. Executive Snapshot missing (completeness fail)
2. Bottom Line missing (completeness fail)
3. Themes too vague — no grounding in data
4. Forward Watch is not actionable
5. RED rating with no justification — what is actually RED here?

**Human review outcome:** Reject. Return to generator with feedback.

---

## Notes for Intelligence Staff

- **Don't overthink it.** A good brief is one the Captain can act on. If you're uncertain, ask yourself: "Would I send this to my boss?"
- **Data first.** Every narrative claim (themes, implications, forward watch) must trace back to at least one signal in the brief's top_events.
- **CPS 230 is always relevant.** Even if this brief's findings are green-level, they still inform the operational resilience picture. State it explicitly.
- **Red ratings are rare.** If you're rating everything RED, you're crying wolf. Reserve RED for "the Captain needs to act today."

---

## Historical Context

This standard was formalized after a period where briefs accumulated in IN_REVIEW status indefinitely because the publication bar was unclear. The automated pre-screen (implemented 2026-07-28) codifies the bar and enables routine publication without human bottleneck on green-level findings.
