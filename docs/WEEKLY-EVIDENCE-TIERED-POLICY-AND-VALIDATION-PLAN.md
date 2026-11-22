# Tiered escalation policy (wk-detect/0.4.0-tiered), holdout plan, sample sufficiency, historical challenge set

Offline only; nothing here is wired to a live path. The model is development-grade: both existing fresh sets have been inspected.

## 1. Tiered operational relevance and escalation rules
**Sector relevance (tier)** weights a stated event; it never escalates on its own.
| Tier | Meaning | Sectors in the lexicon |
|---|---|---|
| 1 | Critical essential services and infrastructure | energy, telecom (incl. emergency calls), health, aviation, transport/water, finance |
| 2 | Systemically important dependencies and supply chains | cloud/software platforms, food supply and retail, government services |
| 3 | Context-dependent services (and anything with no recognised sector) | consumer services/portals, unknown |

**Separate axes** (all fields on `Decision`): sector tier · event type (cyber incident, outage, physical, vulnerability) ·
impact status (confirmed / unconfirmed / retrospective / potential) · operational materiality (high/medium/low) · evidence
confidence · action urgency. Priority is derived:
1. **ESCALATE**: materiality high with solid evidence (primary, mainstream/specialist, or ≥2 independent publishers). High
   means a *stated* consequence at Tier 1, at Tier 2 with scale, or a data-exposure consequence with scale. A single credible
   source gives a *provisional* escalation, marked uncorroborated with a verification follow-up. Also provisional: a Tier 1
   incident described as major/widespread by a credible source even without a stated consequence (severe potential). An
   advisory escalates only with exploitation + known exposure + primary source.
2. **VERIFY**: high materiality on weak evidence (aggregator-only); an unconfirmed incident without a demonstrated consequence
   (Tier 1/2 or a stated compromise of unknown reach); potential high-impact candidates.
3. **WATCH**: medium materiality with solid evidence (e.g. Tier 2 confirmed consequence without scale; exploited advisory
   without known exposure; retrospective reports of Tier 1 events).
4. **REFERENCE**: everything else, including any sector mention with no event.
Commentary, roundups and retrospective items never carry an incident to ESCALATE. No causal links are produced.

**Test cases** (`tests/test_event_detection.py::TestTieredEscalationPolicy`, 11 tests): Tier 1 confirmed outage → provisional
ESCALATE; unconfirmed "investigating a cyber incident" at a retailer → VERIFY; Tier 2 confirmed consequence, no scale → WATCH;
Tier 2 worldwide outage → ESCALATE; Tier 3/unknown breach not auto-escalated by sector; sector-only news (profit, lounge,
appointment) → REFERENCE; retrospective complaints/compensation → not ESCALATE; Tier 1 "major incident declared" →
provisional ESCALATE; the same report from an aggregator only → VERIFY; status-page and physical events become candidates;
all axes exposed separately. Earlier adversarial tests (KEV not critical, syndication, commentary, order independence) remain.

**Known conflict to resolve:** the reviewers' rubric used for holdout2 predates this policy (it marked unconfirmed breaches and
widely used exploited advisories as ESCALATE). Under this policy many of those are VERIFY/WATCH, so escalation recall measured
against those labels (1/11) understates agreement with the Captain's intent. Labels must be re-adjudicated under rubric v2.

## 2. Fresh holdout evaluation plan
1. **Rubric v2** written from §1 (separate sector tier, event type, confirmed/potential, materiality, urgency, expected
   outcome), approved by the Captain before labelling.
2. **Relabel** the 150-event development set and holdout2 under rubric v2 with two blind labellers (development evidence; the
   127-event set stays development evidence only, its original labels and fixture unchanged).
3. **Third holdout** (untouched, drawn only after the model is frozen and committed): two-phase sampling so enough positives exist
   without biasing precision. Phase 1: a recall-oriented screen (broad signal terms) over ≥3 weeks of events yields a candidate
   pool; draw positives-enriched sample from it. Phase 2: a random sample of screen-negatives to estimate what the screen misses,
   so recall is reported on the whole population with weights, not only on the enriched sample.
4. Two blind labellers; report κ, every disagreement, and adjudication by the Captain (not the author). Freeze model hash and
   rubric before labelling; run once.
5. Report separately with denominators and exact intervals: candidate recall, materiality precision/recall, escalation recall and
   precision (incident level), grouping precision/recall/false-merge rate (on a grouping-specific set), review load (VERIFY items/week).

## 3. Sample sufficiency (exact one-sided 95% lower bounds)
Positives needed for the *lower* bound to clear a recall target, by observed misses:
| Target | 0 misses | 1 | 2 | 3 |
|---|---|---|---|---|
| recall ≥ 95% | 59 | 93 | 124 | 153 |
| recall ≥ 90% | 29 | 46 | 61 | 76 |
Precision ≥ 85% needs flagged-high events of: 19 (0 FP), 30 (1), 40 (2), 50 (3).
**Holdout2 is insufficient:** it had 10–15 reviewer-marked high-impact events and 9–11 escalations, far below 59, so no recall
target could be supported even with zero misses. At the observed prevalence (about 6–9% of events) 59–124 positives need
roughly 650–2,000 events at random, which is why the two-phase enriched design above is needed. Incident-level escalation positives
will be fewer than event-level ones, so the count must be of incidents.

## 4. Historical critical-incident challenge set (research plan)
Purpose: a challenge set of real, independently verifiable events plus false alarms, kept separate from the sampled holdouts and
reported as its own stratum (it measures recall on known-critical events, not prevalence).
* **Inclusion rule:** an incident is included only with ≥2 independent public sources, at least one official (regulator, vendor
  post-incident report, government advisory) and one mainstream outlet, recorded with URL, publisher and date by a human
  researcher. The headline text used for evaluation is the real publisher headline, never reconstructed.
* **Categories and unverified candidates from model memory** (each must be confirmed before use): global platform outages
  (CrowdStrike/Windows July 2024; AWS us-east-1 Oct 2025; Cloudflare Nov 2025), telecom outages (Optus Nov 2023), health/finance
  breaches (Medibank 2022, Change Healthcare 2024, Latitude 2023), supply-chain compromise (SolarWinds 2020, Kaseya 2021, MOVEit
  2023), critical vulnerabilities with exploitation (Log4Shell 2021), infrastructure and physical events (Colonial Pipeline 2021,
  Heathrow substation fire 2025, Iberian blackout 2025), retail incidents (M&S/Co-op 2025).
* **False-alarm and routine controls:** vendor marketing, awards, KEV-only listings with no exposure, earnings news from Tier 1
  firms, hoax or retracted outage claims, retrospective follow-ups. At least as many negatives as positives.
* **Method:** research by a worker using public web sources (approval needed for web access beyond the database); a second
  reviewer verifies each entry; disagreements go to the Captain.

## 5. Status
Supabase sampling is complete (160 events). The 150- and 127-event review-sheet worker is still blocked on its own permission
prompt, which only the user can answer. Both blind labellers finished (κ 0.79–0.84).
