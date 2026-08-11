# XO Telegram Message Usefulness + Outage-Threshold Push — Design Proposal

**Requested by:** Captain TJR, 2026-08-09, following tonight's misleading/confusing Telegram alerts (separately being fixed — see `.claude/skills/bot-reviews/eod-alert-verification/chief-engineer-review.md` for the "never_succeeded" false-alarm and Content Review naming-mismatch verification).
**Authority:** Chief Engineer, USS-TJR-003, Engineering Division — Advisory only.
**Scope:** Design and investigation only. **No code changed.** Everything below needs Captain sign-off before implementation, per the mission brief.

## Mission Summary

Two requests: (1) a prioritized, concrete list of Telegram message-quality improvements for XO's scheduled pushes, grounded in the real generator code; (2) a proposal for a proactive push when outage-related intelligence signals cross a severity/confidence threshold, instead of sitting silently in the content queue — with a real threshold (not a guess) and a wiring plan that reuses existing notification infrastructure.

## What was verified (method)

Read in full: `intelligence/captains_brief.py` (726 lines), `core/platform/infra_narrative.py` (146 lines), `intelligence/scheduler.py` (825 lines, all APScheduler job registrations), `core/platform/attention_engine.py`, `core/platform/interrupt_dispatcher.py`, `core/platform/event_bus.py`, `core/platform/notification_service.py`, `intelligence/classification/classifier.py`, `intelligence/ranking/ranker.py`, `intelligence/persistence/intelligence_store.py`, `intelligence/content_intelligence_service.py`, `intelligence/classification/content_classifier.py`. Confirmed `platform-runtime/proactive_scheduler.py` and `platform-runtime/captain_notifications.py` are **dormant** — they only run inside `platform-runtime/app.py`'s Slack Commander process, which prior sessions confirmed is currently shut down (XO-only Telegram policy, 2026-07-05); `telegram-bots/xo/app.py` itself registers no APScheduler jobs and explicitly defers to `python -m intelligence.scheduler` for all proactive pushes. So the live proactive-push surface is entirely `intelligence/scheduler.py` → `intelligence/captains_brief.py` (+ `infra_narrative.py`).

Ran live SQL against the production Supabase project (`cjvrpjwewsrumnbdydgg`) to ground Part 2's threshold in real 30-day data rather than a guess — see Part 2.

---

## Part 1 — Telegram message usefulness

### 1.1 What's live today

`intelligence/scheduler.py` registers these Telegram-facing jobs (all real, all currently scheduled):

| Job | Cron (AEST) | Generator |
|---|---|---|
| Morning brief | 07:00 daily | `captains_brief.generate_morning_brief()` |
| Midday check (conditional) | 12:30 daily | `captains_brief.generate_midday_update()` |
| EOD summary | 18:00 daily | `captains_brief.generate_eod_summary()` |
| Weekly report | Mon 07:00 | `captains_brief.generate_weekly_report()` |
| Knowledge Platform digest | 08:00 daily | `captains_brief.generate_knowledge_ops_brief()` |
| Weekly debrief digest | (wired, not cron-scheduled in this file — called elsewhere) | `captains_brief.generate_weekly_debrief_digest()` |
| Validation-suite regression alert | daily 06:30 job, conditional | `notify()` direct, via `Severity.CRITICAL` |
| INTERRUPT_NOW pushes | every 10 min (`continuous_attention_evaluation`) | `interrupt_dispatcher.dispatch_interrupt_now()` → `notify()` |

Each brief embeds an `infra['narrative']` block sourced from `core.platform.infra_narrative.generate_infra_narrative()` when `state == "unsure"`.

### 1.2 Assessment against the stated usefulness criteria

**Most important thing first?** Partially. Morning/EOD both lead with Capacity, which is right for a personal-ops brief, but INTELLIGENCE/PLATFORM HEALTH — the sections most likely to contain something urgent — sit in the middle, and their inclusion is conditional (silence = nothing to report), which is the correct pattern *when the underlying signal is reliable*. Part 2 below shows the signal feeding this section (`rank_score`) is not reliable for outage-class events, so "nothing shown" can mean "nothing happened" or "something happened but scored too low to surface" — indistinguishable to the Captain today.

**Severity/urgency visually distinguishable at a glance?** Inconsistent. Three different severity vocabularies coexist in the same message family: `_risk_emoji()` (🔴🟡🟢⚪ for HIGH/MEDIUM/LOW, intelligence signals only), `_priority_label()` (🔥⚡📌📎 for P0–P3, missions only), `_cap_emoji()` (🟢🟡🔴 for capacity score, inverted thresholds vs. risk). A Captain skimming a 15-line message on a phone has to remember three separate icon grammars. This mirrors a UX finding already logged elsewhere in this platform (MSN-0320: "5+ severity vocabularies") — it's the same defect at the Telegram layer.

**Anything vague/non-actionable?** Yes, concretely:
- `generate_knowledge_ops_brief()` (`captains_brief.py:547-556`) is the good example — "🛑 Permanently failed: **N** — worker.py override to force another attempt" states the number *and* the action. Nothing else in the file does this consistently.
- The infra-narrative block (`infra_narrative.py:40-48`, `_SYSTEM_PROMPT`) instructs the LLM to narrate *what's* degraded and the likely impact, but never instructs it to say **what the Captain should do about it** (or that nothing needs doing because it's already being handled/monitored). This is a direct contributor to tonight's confusing alert — see the cross-referenced verification doc for the specific false "no data has ever been recorded" overstatement this produced. That review's Recommendation 1 already covers *constraining* the prompt against overstatement; this review adds the complementary half: the prompt should also require a **stated next action or explicit "no action needed"**, not just avoid inventing severity.
- `_get_content_review_queue()` items render as `📝 <b>{title}</b>  [{status} · {pillar}]` (`captains_brief.py:409-415`, `503-509`) — a bare title/status/pillar with zero indication of *why* it's there or how stale it is. The verification doc found one item (`68b17461`, the Telstra draft) that had been sitting in `ready_to_publish` for **four weeks** with this exact rendering never once flagging its age.

**Duplicated across sections?** Yes, at the code level, which then produces duplicated *content* at the message level. `content_queue` rendering is copy-pasted verbatim between `generate_morning_brief()` (`captains_brief.py:408-415`) and `generate_eod_summary()` (`captains_brief.py:502-509`); the `infra`/Platform Health block is copy-pasted verbatim between the same two functions (`399-404` and `495-500`). Net effect: if nothing changed between 07:00 and 18:00, the Captain sees the identical Content Review list and identical Platform Health warning twice in the same day, with no "unchanged since this morning" framing — and any future formatting fix to either block has to be made in two places (already a source of drift risk on this platform per prior missions).

**Formatting fighting or working for a phone screen?** Mostly working — `<code>` blocks for progress bars render monospace correctly in Telegram, and one emoji per section header is a reasonable density. The one real issue: `snap[:400]` / `fw[:300]` style hard character truncation (`captains_brief.py:380`, `589`, `601`) cuts mid-sentence with no ellipsis or boundary awareness, producing dangling fragments on longer ORI brief snapshots.

### 1.3 Data available but not surfaced

Checked what exists in the schema vs. what these generators read:
- **Decision records exist and are unused.** Four decision-related tables have real, current rows: `decision_records` (31), `decisions` (65), `commander_decisions` (61), `decision_outcomes` (6). None of `captains_brief.py`'s `_get_*` fetchers touch any of them — there is no "pending/forgotten decision" section in any live brief. `platform-runtime/captain_notifications.py::get_forgotten_decisions()` (dormant, Slack-only, file-scanning based on `decision-register.txt`/ADR markdown rather than the Supabase tables) is the closest prior art — it is not a drop-in port (different data source, heuristic parsing, would need its own verification pass), but its *shape* (age-sorted, stale-decision surfacing) is worth reusing conceptually for a Supabase-backed version.
- **Mission status changes (deltas) are not tracked.** `_get_active_missions()` returns a point-in-time snapshot (`title`, `status`, `priority`, `department`) every time — there's no "changed since yesterday's brief" comparison, so a mission that flipped from `in_progress` to `blocked` overnight looks identical to one that's been sitting untouched for weeks.
- **No deadline field exists to surface.** Checked the `missions` table schema directly — there is no `due_date`/`deadline` column at all, so "upcoming deadlines" is not a real gap in the generator, it's a real gap in the schema. Not actionable without a separate schema change; noted so it isn't mis-filed as a quick brief fix.

### 1.4 Prioritized, concrete recommendations

**P1 — Fix the vague infra-narrative prompt to require a stated action.**
File: `core/platform/infra_narrative.py:40-48` (`_SYSTEM_PROMPT`).
Add to the existing prompt (after the existing "Rules:" line): *"Always end with one explicit line stating either what the Captain needs to do right now, or that this is already being monitored/handled automatically and needs no action."* This composes directly with the already-flagged fix in `eod-alert-verification/chief-engineer-review.md` Recommendation 1 (which constrains the prompt against overstating `never_succeeded` as data loss) — implement both edits to the same prompt string together, not as two separate passes.

**P1 — Stop duplicating the Content Review and Platform Health blocks; make repeats explicit instead of silent.**
File: `intelligence/captains_brief.py`. Extract lines `399-404`/`495-500` into a shared `_format_infra_block(infra) -> list[str]` and lines `408-415`/`502-509` into `_format_content_review_block(content_queue) -> list[str]`, called from both `generate_morning_brief()` and `generate_eod_summary()`. While doing this, add a same-day repeat marker: if the EOD block's content matches what the morning brief already showed (compare title sets), prefix the EOD section header with "(unchanged since this morning)" instead of re-listing identically — cheap to compute since `_persist_brief()` already stores the morning brief text/signal count for the day.

**P2 — Add an explicit "why this matters" / age signal to Content Review items.**
File: `captains_brief.py:409-415`, `503-509`. Currently: `📝 <b>{title}</b>  [{status} · {pillar}]`. Proposed: `📝 <b>{title}</b>  [{status} · {pillar} · {age}]` where `age` is a simple "Nd old" computed from `draft_generated_at` (already selected in the query at `captains_brief.py:154`, just not rendered). A draft sitting for 4 weeks should visibly read as stale, not identical to one generated an hour ago — this is the exact gap the verification doc's Recommendation 4 flagged opportunistically for the specific Telstra item; this generalizes it into the render function so it doesn't require a one-off catch next time.

**P2 — Unify severity iconography or explicitly document why it differs.**
Consolidate `_risk_emoji()`, `_priority_label()`, and `_cap_emoji()` (`captains_brief.py:277-294`) around one shared visual grammar — e.g. a single 🔴🟡🟢 hierarchy used consistently, with mission priority (P0–P3) mapped onto the same three-color scale rather than a fourth separate icon set (🔥⚡📌📎). If the Captain genuinely wants missions visually distinct from risk/capacity (a legitimate design choice, not obviously wrong), make that a documented decision rather than an accident of incremental feature addition — three vocabularies growing to four with the next feature is how this kind of drift compounds.

**P3 — Truncate at a sentence/word boundary, not a raw character count.**
`captains_brief.py:380`, `589`, `601` (`snap[:350]`, `snap[:400]`, `fw[:300]`) — replace with a small `_truncate(text, n)` helper that backs off to the last `. ` or space before the limit. Low effort, removes a recurring readability paper-cut on longer ORI narrative snapshots.

**P3 (backlog, not urgent) — Consider surfacing stale/pending decisions.**
Given `decision_records`/`decisions` have 31/65 real rows and zero current Telegram surfacing, a future `_get_stale_decisions()` fetcher + weekly-report section is plausible — but this needs its own short investigation first to establish which of the four decision tables is canonical (this platform has a documented pattern of concept duplication across near-identical tables; picking the wrong one would surface stale/duplicate data). Flagging as backlog, not proposing a specific implementation here.

---

## Part 2 — Outage-threshold push notification

### 2.1 Where outage signals are actually detected and scored today

`intelligence/classification/classifier.py:36-42` assigns `event_type = "technology_outage"` or `"telecom_outage"` via keyword rules (`outage`, `incident`, `degraded`, `telstra`, `optus`, `nbn`, etc. — `classifier.py:36-42`). The same function computes, per event:
- `operational_relevance` (0.0–1.0) — category-based base score, boosted for AU geography and `_HIGH_IMPACT_KEYWORDS` hits (`classifier.py:149-153`, `214-222`).
- `customer_impact` ("low"/"medium"/"high") — **"high" only when the text contains one of** `critical, severe, major, significant, widespread, nationwide, national outage, extended outage, data breach, ransomware, zero-day, emergency, evacuation, fatalities, mass disruption` (`classifier.py:149-153`, `225-226`) — this is the genuine severity signal, distinct from relevance.
- `confidence` (0.0–1.0) — `source_confidence_weight * 0.7 + min(keyword_hits, 5) * 0.06` (`classifier.py:290-292`) — measures how sure the classifier is this is a real, well-corroborated match, not how severe the event is.

`intelligence/ranking/ranker.py:1-18` then computes `rank_score` (0–100), a **composite** weighted 25% source priority, 20% operational impact, 15% customer impact, 15% banking relevance, 10% CPS230 relevance, 10% cross-source confirmation, 5% geography — i.e. a score built for the ORI (banking/regulatory-resilience) brief's ranking use case, not a general urgency score.

There is already a working escalation tier elsewhere in this codebase: `core/platform/attention_engine.py`'s `AttentionThresholds` (`interrupt_importance_floor=75`, `interrupt_confidence_floor=70`, 0–100 scale) routes any event to `INTERRUPT_NOW`, and `core/platform/interrupt_dispatcher.py` already pushes those via `notification_service.notify()` over Telegram every 10 minutes (`intelligence/scheduler.py:647-696`, `_attention_evaluation_job`). Every `intelligence_events` row — including every outage event — is already mirrored into `core_events` on save (`intelligence/persistence/intelligence_store.py:280-293`, `save_event()`), with `importance = round(rank_score)`, `confidence = round(confidence*100)`, `relevance = round(operational_relevance*100)`. **So the existing INTERRUPT_NOW push path structurally already covers outage events in principle — it's just gated on `rank_score`, and live data shows `rank_score` almost never crosses a usable threshold for this event type (see 2.2).**

Separately, `intelligence/content_intelligence_service.py` + `intelligence/classification/content_classifier.py` score the same events for **content-writing relevance** (which pillar to blog/post about, `suggested_angle`) and persist to `content_signals` → (via `core/content/draft_worker.py`, not read this pass) → `comms_content`. This is a completely different pipeline with a different purpose (what to write about, not what to alert on) — it is *not* wired to `core_events`, the Attention Engine, or `notify()` at all. The "Telstra outage is a stark reminder..." draft the Captain saw came from this content pipeline (`content_classifier.py:156`: `(["outage", "disruption", "incident"], "Lessons from this disruption for building resilient operations")` is the literal angle template that produced it) — confirmed by the sibling verification doc as `comms_content` id `68b17461`, sitting in `ready_to_publish` since 2026-07-12, four weeks with no push of any kind. This confirms the Captain's framing exactly: a real outage-related signal sat in a content queue with zero connection to any alerting mechanism.

### 2.2 Real data — why the obvious threshold (reuse the existing INTERRUPT_NOW floor) doesn't work

Queried `intelligence_events` on the live Supabase project (`cjvrpjwewsrumnbdydgg`) for `technology_outage`/`telecom_outage` events over the last 30 days (297 rows total, 288 `technology_outage` + 9 `telecom_outage`):

| Field | Finding |
|---|---|
| `rank_score >= 75` (the existing `INTERRUPT_NOW`/HIGH floor) | **0 of 297** |
| `rank_score >= 50` (the existing MEDIUM floor / "new signal" floor used in `_get_new_signals_since`) | **1 of 297** |
| `operational_relevance >= 0.80` | 288 of 297 (97%) |
| `confidence >= 0.70` | 106 of 297 (36%) |
| `confidence >= 0.65` | 258 of 297 (87%) |
| `customer_impact = 'high'` | **15 of 297 (5%)**, of which 14 are AU-geography |
| avg `operational_relevance` where `customer_impact='high'` | 0.98 |
| `customer_impact='high' AND confidence >= 0.70` | 5 of 15 |
| `customer_impact='high' AND confidence >= 0.65` | 11 of 15 |

Two things this proves:
1. **`rank_score` cannot be the outage-alert gate.** It's a composite dominated by source-priority/banking/CPS230 weighting that outage news from general media sources structurally can't reach — the maximum `rank_score` for *any* outage event in 30 days was 52.2. Reusing the existing INTERRUPT_NOW floor (75) or even the MEDIUM floor (50) as-is would mean this feature never fires, silently, which is exactly the failure mode already observed. This also means the *existing* "📡 INTELLIGENCE (24h)" section of the morning/EOD brief (which orders by `rank_score`) can silently push a real outage out of its top-5 display in favour of a routine higher-`rank_score` regulatory item — a second, independent consequence of the same root cause, worth the Captain's awareness even though it's a Part 1-adjacent finding.
2. **`operational_relevance >= 0.80` alone is too broad** — it fires on 97% of all outage-classified events, which is not a threshold, it's "alert on almost everything typed as an outage." **`customer_impact = 'high'` is the real severity signal** — it only fires on keyword-evidenced severe/widespread/critical language, matches 5% of events, and correlates almost perfectly with genuinely high relevance (0.98 avg) and AU-domestic events (14/15).

### 2.3 Proposed threshold

> **Fire a push when `event_type IN ('technology_outage', 'telecom_outage')` AND `customer_impact = 'high'` AND `confidence >= 0.65`.**

Reasoning: `customer_impact='high'` is the field that actually encodes severity (widespread/critical/major language), not `rank_score` or bare `operational_relevance` (both shown above to be unusable — too flat/never-crossing or too broad, respectively). `confidence >= 0.65` is a minimum-corroboration floor set just below the existing 87% coverage line for this event population, rather than the existing platform-wide `interrupt_confidence_floor=70`, which live data shows would cut genuine severe events from 15 to 5 (67% false-negative rate) — precisely the "wrong threshold means missed real outages" risk this mission was explicit about avoiding. At `>=0.65`, 11 of 15 real severe events over 30 days would have fired (~1 push every 2.7 days) — a low, sustainable cadence, not alert fatigue.

**This is a recommendation for Captain approval, not a final number.** Two adjacent choices the Captain may want to weigh in on directly:
- Lowering to `confidence >= 0.60` would likely recover most/all of the remaining 4 events (not queried at that exact cut) at the cost of a slightly higher false-positive risk — worth a follow-up query if the Captain wants to see the marginal cases before deciding.
- Whether to include `energy_disruption` (61 events/30 days, narrower confidence band 0.63–0.74, `customer_impact` distribution not yet queried this pass) in scope now or as a Phase 2 addition once the `technology_outage`/`telecom_outage` threshold has run for a couple of weeks and proven itself.

### 2.4 Wiring plan (composition-first — no new sender)

Per this platform's own composition-first principle and this mission's explicit instruction, this reuses `core.platform.notification_service.notify()` (the platform's canonical Telegram sender, already live via `interrupt_dispatcher.py` and the validation-suite job) — **no new bespoke sender is proposed.**

Two wiring options considered:

**Rejected: extend `core/platform/attention_engine.py`.** The Attention Engine's own docstring (`attention_engine.py:1-20`) is explicit that it is "a thin, pure routing table, not a rule engine that guesses at domain semantics; scoring the raw fields is the emitting domain's job." Adding an outage-specific `customer_impact` rule inside it would violate that stated boundary, and `attention_engine.py` is a shared platform-wide module any change to which — per Chief Engineer escalation rules — is a platform-wide decision requiring its own separate sign-off, not something to fold into this change. Also, the current `core_events` mirror (`intelligence_store.py:280-293`) doesn't even carry `customer_impact` or the original ORI `event_type` onto `core_events` — only `rank_score`/`confidence`/`operational_relevance` survive the mirror — so this option would additionally require widening that mirror's `metrics` payload, a second platform-wide-adjacent touch point.

**Proposed: a small, domain-owned check inside `intelligence/persistence/intelligence_store.py::save_event()`.** Add a new helper, e.g. `_maybe_push_outage_alert(event: RankedEvent) -> None`, called from `save_event()` immediately after the existing `_publish_core_event(...)` call (`intelligence_store.py:280-293`), guarded the same way every other call in that function already is (best-effort, never raises, never affects the row's own persistence). Logic: if `event.event_type in ("technology_outage", "telecom_outage")` and `event.customer_impact == "high"` and `event.confidence >= 0.65`, call `notification_service.notify(body=event.raw_title, title=f"Outage — {event.event_type}", severity=Severity.ALERT, template="alert", transport=Transport.TELEGRAM)`.

Why this location, not the scheduler jobs: `save_event()` is the single choke point every ranked event passes through regardless of which job found it — `_daily_collection_job` (06:00), `_intraday_status_collection_job` (every `INTRADAY_STATUS_INTERVAL_MINUTES`, default 180 min — the fast-moving-status-feed poller added 2026-08-09 specifically for outage/status pages), and the GitHub brief sync. Hooking `save_event()` once covers all of them instead of duplicating the check into each job's loop. Deduplication is inherited for free: `save_event()` is only ever called by its callers *after* they've already filtered out anything matching an existing `dedup_hash`/`canonical_url`/title+date (`scheduler.py:440-464`, `543-563`) — so a still-unfolding outage story re-appearing in the next intraday poll does not re-trigger a push, only a genuinely new article does. This is domain-owned code (the ORI intelligence domain deciding when its own signals are alert-worthy), consistent with Attention Engine's own stated boundary, and touches no shared platform module — so it does not itself need platform-wide escalation, though the Captain's explicit approval of the threshold value is still required per this mission's framing before it goes live.

**Not proposed:** wiring anything through the `content_signals`/`comms_content` pipeline. That pipeline answers "what should the Captain write about," a slower/curatorial question — collapsing it into the alert path would conflate two different purposes the platform already keeps separate for good reason (drafts don't need to interrupt; genuine outages do). The two pipelines should stay decoupled; this fix targets the alerting gap directly at the source (`intelligence_events`), not by routing the content pipeline into an alert.

## Open items / not addressed

- Exact copy for the outage push body/title above is a starting draft, not final — the Captain may want a different title format or a link to `canonical_url` included (data is already on `RankedEvent`, trivial to add).
- No query was run yet for the `energy_disruption` `customer_impact` breakdown (flagged in 2.3) — a 5-minute follow-up if the Captain wants energy included in scope now rather than Phase 2.
- This document does not touch or duplicate `eod-alert-verification/chief-engineer-review.md`'s own recommendations (the `never_succeeded` overstatement fix, the `vm-processing-healthcheck.service` missing-directory bug, the Content Workbench mobile-default-stage bug) — cross-referenced where relevant, not re-litigated.

## Mission Status

Advisory only. Design and investigation complete; no code changed. Both parts need explicit Captain sign-off before implementation — Part 2 in particular per the mission's own instruction not to pick the final threshold unilaterally.
