# XO Telegram Brief Review — Morning / EOD / Weekly, post tonight's rework

**Reviewer:** XO, companion-mode product review (per `.claude/skills/xo/SKILL.md`).
**Date:** 2026-08-10 (reviewing tonight's 2026-08-09/10 rework of `intelligence/captains_brief.py`).
**Method:** Sourced `telegram-bots/xo/.env`, imported `generate_morning_brief` / `generate_eod_summary` / `generate_weekly_report` from `intelligence.captains_brief` directly, called them against live Supabase (no mocking, no Telegram send). Cross-referenced against live row counts/recency in the tables named in the brief, queried directly via the Supabase MCP against project `cjvrpjwewsrumnbdydgg` (USSTJR). Full generated text is in the Appendix.

This is a design review, not a bug hunt — but two of the findings below are bugs (one live, one about to go live), not taste calls.

---

## Top-line verdict

Tonight's Part 1 fixes (de-duped blocks, age on Content Review, unified severity icons, word-boundary truncation) hold up under live data — verified below. The weekly redesign (drop missions/decisions, real 7-day OSINT roll-up with LLM exec summaries) is a real improvement and reads well. But the weekly report's new **Capacity** section is silently and permanently broken — it queries a table nobody has written to in six weeks — and that bug was sitting right next to the fix that was supposed to have already caught this exact failure mode once. That's the finding to act on first.

---

## 1. Message-by-message read

### Morning Brief (generated live, see Appendix)

Leads with Capacity (recovery-pulse based, 33% confidence, one pulse logged today), then Intelligence (4 items, all correctly ⚪/🔴/🟢-tagged), then Platform Health (correctly showing the two genuinely-degraded domains — verified against `verification_state`, see §2), then Content Review (4 items, correctly showing age).

This is the right order for a 07:00 message — capacity first is correct, and it's honest: recovery confidence is 33% ("Multiple pulses missing") and the brief says so plainly rather than dressing it up. Good.

One redundancy candidate, not a real problem today: the Intelligence section fell into its primary branch (real signals from the last 24h) rather than the ORI-brief fallback, so I can't verify the fallback text quality live today — worth a spot-check on a quiet news day when it does trigger, since that branch's `_truncate_clean(snap, 350)` output has had truncation bugs before (fixed tonight, per `8fd07bec`).

### EOD Summary

Structurally near-identical to Morning by design (shared `_format_infra_block`/`_format_content_review_block` helpers) — that's the point of tonight's de-dupe fix, and it works: both Content Review and Platform Health correctly rendered `(unchanged since this morning)` in the live EOD text because nothing changed since 09:08 this morning (both runs happened minutes apart in this test, but the substring-match logic is doing real work, not just always-true — see the code path in `_format_content_review_block`/`_format_infra_block`).

**But the marker doesn't go far enough.** Even flagged "(unchanged since this morning)", the EOD Content Review block still repeats all 4 full item lines (title, status, pillar, age) verbatim. The Captain already read this exact list 12 hours earlier. A Captain glancing at his phone at end of day is being shown the same 4-line block twice in one day with only a small italic annotation distinguishing it. If it's genuinely unchanged, the EOD version should collapse to something like `✍️ CONTENT REVIEW — unchanged since this morning (4 items)` with no item list, and only expand to the full list when something actually moved. Right now "unchanged" gets you a label, not a shorter message.

Also worth noting: EOD's `<b>⚡ TODAY</b>` capacity block (the `captain_capacity_rating`-based one, separate code path from `RECOVERY PULSES`) didn't render at all in this live run — `_get_todays_health()` returned nothing. See §2, this isn't a one-off: it can't render, ever, in current data reality.

### Weekly Report

The redesign is good. Two separate LLM exec summaries (Tech OSINT, Health OSINT) genuinely synthesize rather than list — the live output correctly identified "Cloudflare Status reports... Workers, R2, and Gateway" as the dominant Tech OSINT theme and "ClinicalTrials.gov... vaccine development... cardiovascular... mental health" for Health OSINT, both grounded in what's actually in the data (spot-checked against the raw counts, see §2). This is a real improvement over a raw count dump.

**But `CAPACITY THIS WEEK` is dead on arrival.** Live output: *"No capacity logs this week."* It will say this every week from now on. See §2 for why — this isn't a quiet week, it's a table that stopped being written to in June.

`CONTENT THIS WEEK` correctly reflects real weekly activity (2 published, 3 in review, 1 ready-to-publish) — this is a genuinely useful section the standing Content Review queue doesn't give you (a *rate*, not just a snapshot).

---

## 2. What's missing / what's broken — checked against live data, not guessed

I queried every table named in the brief for row counts and most-recent-activity. Findings, in order of how much they matter:

### 2a. `generate_weekly_report()`'s Capacity block queries a dead table — real bug, not a data gap

`_get_weekly_capacity()` (captains_brief.py:360-369) queries **only** `captains_log_entries`. Live query:

```
select log_date, captain_capacity_rating from captains_log_entries order by log_date desc limit 6;
```
→ most recent row: **2026-06-28**. Table has 6 rows, total, ever. Six weeks stale as of today (2026-08-10).

Meanwhile `_get_todays_health()` — the *daily*-brief equivalent — queries the same dead table, gets nothing, and both Morning and EOD **already have a working fallback**: Morning falls to `recovery_confidence_today` (the `elif recovery and recovery.get("pulses_completed", 0) > 0:` branch), and that's exactly what fired in my live run (33% confidence, "Multiple pulses missing"). EOD has the same fallback via `RECOVERY PULSES`.

The weekly block has no such fallback. It's the one place in the file that still trusts `captains_log_entries` unconditionally, and it's the one place where that trust silently produces "No capacity logs this week" forever, not a graceful degrade.

This is the *exact* failure class `_rating_emoji`'s own docstring says was already found and fixed once (captains_log_entries.captain_capacity_rating query was 400ing silently) — it recurred in the new weekly code path because the weekly capacity block was built as new code, not by extending the existing (already-fixed) fallback logic.

**Fix is cheap:** `_get_weekly_capacity()` should pull from `recovery_pulses` (or `recovery_confidence_today`-style daily aggregation) the same way Morning/EOD already do, not from `captains_log_entries`.

**Bonus finding while verifying this:** even `recovery_pulses` itself, queried for the trailing 7 days, returned **1 row** — today's morning pulse. The prior entries are sparse singles on 07-27, 07-23, 07-18, 07-15, then nothing between those and today. Recovery-pulse logging has effectively been dormant for three weeks and only resumed today. If the weekly block is fixed to read `recovery_pulses`, the honest first output will be "1 pulse logged this week" — which is a genuinely useful (if uncomfortable) signal about pulse-logging adherence that the Captain currently has no visibility into at all, daily or weekly. Worth surfacing rather than just fixing the query silently.

(For completeness: I also checked `captain_readiness_history`, the other candidate daily-trend table — also stale, frozen at identical values 2026-07-10 through 2026-07-19, not a viable substitute either.)

### 2b. Outage-push-alert activity never appears in any of the 3 messages — judgment call, leaning toward "add a one-liner"

Tonight's Part 2 feature (`_maybe_push_outage_alert` in `intelligence/persistence/intelligence_store.py`) fires a standalone Telegram push via `notification_service.notify()` whenever an `intelligence_events` row has `event_type IN ('technology_outage','telecom_outage') AND customer_impact='high' AND confidence>=0.65`. I re-ran that exact filter live:

```
4 qualifying events in the last 7 days, 3 since the feature actually shipped (2026-08-09):
- 2026-08-09 07:02 — "Serverless Inference - Gemma4 Latency Issues..." (confidence 0.71)
- 2026-08-09 04:08 — "Degraded performance on loading pages and facing API errors" (confidence 0.66)
- 2026-08-09 04:08 — "Projects in stuck state in EU-CENTRAL-1 (Frankfurt)" (confidence 0.69)
- 2026-08-04 20:00 — "Trump wants 'fair treatment' in fight over Labor's levy on tech giants..." (confidence 0.67)
```

Two things follow from this:

**First, a design question the Captain should decide, not me:** none of the 3 regular briefs reference this activity at all. A separate always-on push for genuine outages is a defensible design on its own (that's what it's for — don't make the Captain wait until morning for something urgent). But there's currently **no durable record of what fired** — `notification_service.notify()`'s only bookkeeping is an in-process `_CALL_LOG` list (`core/platform/notification_service.py`), which doesn't survive a process restart and isn't queryable. If the Captain wants to be able to ask "how many outage pushes did I get this week, and were they real," the only way to answer that today is to re-run the same `intelligence_events` filter I just ran — which is cheap and could be a one-line addition to the weekly report (`"🚨 N outage alert(s) pushed this period"`), separate from the standing OSINT roll-up. I'd lean toward adding it — it's nearly free and closes a real audit gap — but this is explicitly a call for the Captain, not an obvious bug.

**Second, and more urgent: one of the 4 qualifying events is a misclassification riding the new alert path.** The 2026-08-04 "Trump... Labor's levy on tech giants" row is a political/regulatory news story, not a technology outage, but it's tagged `event_type='technology_outage'`, `customer_impact='high'`, `confidence=0.67` — which means it would have crossed the outage-push threshold had the feature existed on 2026-08-04. This isn't a hypothetical: the classifier that assigns `event_type`/`customer_impact` (`intelligence/classification/classifier.py`) is upstream of both the weekly OSINT roll-up *and* the new push feature, and this row shows it can mis-tag a general news story as a severe outage. Worth a classifier accuracy check on `technology_outage` specifically before trusting the push feature's signal-to-noise at scale — right now it's 3-real/1-questionable out of 4, a small sample, but the failure mode is exactly the kind that erodes trust in a push channel fast.

### 2c. Everything else I checked against the live data actually holds up — noted so the negative isn't assumed

- **Decisions correctly removed from the weekly report.** `decision_records` last write: 2026-06-14 (31 rows, 8 weeks dead). `commander_decisions` and `decisions` tables are separate/still-live-ish but weren't the ones cited as broken — the removal commit's framing checks out against the table it names.
- **Missions correctly absent from Morning/EOD** — this was explicit Captain direction (`96e181ee`), not something for me to second-guess; weekly's mission section was left alone per that same commit and I didn't find evidence it should be revisited.
- **Knowledge Library (`processing_documents`, 850 rows, actively growing) is not a gap** — it has its own dedicated, separately-scheduled message (`generate_knowledge_ops_brief`, wired into `intelligence/scheduler.py` as its own job, `id="knowledge_ops_brief"`). Confirmed deliberate separation, not an oversight.
- **Platform Health narrative is accurate, not decorative.** Live `verification_state` (6,665 rows) top row at generation time showed `state='unsure'`, `degraded_domains=[insight_outcomes, morning_brief]` — this is exactly what both Morning and EOD rendered. The LLM narrative isn't inventing anything; it's narrating a real, current degraded state.
- **`human_systems_recommendations` (41 rows) is not a live gap** — last write 2026-06-28, same dead window as `captains_log_entries`. Correctly absent from all 3 messages; nothing to surface.
- **`comms_content` weekly window logic is sound** — `_get_weekly_content_activity`'s live output (6 items: 2 published, 3 review, 1 ready_to_publish) matches a direct query of `comms_content` ordered by `updated_at` over the same 7-day window.

### 2d. Minor, worth a look but not urgent: Tech OSINT confidence coverage

Live query of `intelligence_events` over the last 7 days: **356 of 592 rows (60%) have `osint_confidence_level = NULL`.** The weekly report discloses this honestly (`⚪ 354 unscored` in the severity line — close to my count, small timing skew), which is the right instinct — it's not hiding the gap. But it's worth checking *why* the Tech OSINT confidence-scoring pipeline leaves 60% of events unscored, especially by contrast: `health_signals` over the same window has **zero** nulls on the equivalent `confidence_level` field (170 low / 149 medium / 3 high, fully scored). That's not a Telegram-message problem, it's upstream in the Tech OSINT classification pipeline, but it means 60% of the "TECH OSINT (590)" count the Captain sees is presently un-triaged data.

---

## 3. Consistency check — does the icon unification actually hold across all 3 messages?

Tonight's Part 1 item 4 collapsed three independent severity vocabularies into one `_SEVERITY_EMOJI = {"red": 🔴, "yellow": 🟡, "green": 🟢, "none": ⚪}` table, reused by `_risk_emoji` (intelligence signals), `_rating_emoji` (capacity), and `_priority_label` (missions, though missions are no longer rendered in these 3 messages). I checked this against the live output, not just the code:

- **Holds correctly for signals ↔ capacity ↔ weekly OSINT severity.** Morning's `🔴` on "Armed officers to bolster security..." and the weekly report's `🔴 16 high` use the literal same function (`_risk_emoji`), confirmed by reading `_format_weekly_osint_block`'s call site. One grammar, three places, genuinely unified.

- **Does not hold for content-status icons, and this is visible within a single message.** `_format_weekly_content_block`'s `status_emoji` table (`{"published": "✅", "ready_to_publish": "🟢", "approved": "🟡", "review": "📝"}`) reuses 🟢 and 🟡 — the exact glyphs that mean "low severity" / "caution, medium severity" everywhere else in the same message — to mean "workflow stage," not severity. It shows up concretely in the live weekly output: the **same message** contains `🟢 211 low` (Tech OSINT severity) and `🟢 <b>The Telstra outage is a stark reminder...</b> [ready_to_publish]` (content status) two blocks apart. A Captain who has just trained himself to read 🟢 as "fine, don't worry about it" in the OSINT block sees the identical glyph two lines later meaning "this draft is ready for you to act on" — the opposite of "don't worry about it." The icon-unification effort covered risk/capacity/priority but didn't extend to the content-status vocabulary that sits in the same messages, so the "one shared grammar" claim doesn't fully hold at the whole-message level, only within the signal/capacity family.

**Recommendation:** either give content status a visually distinct glyph family (it already partly does — 📝/✅ are fine, it's just 🟢/🟡 that collide) or accept the collision as low-risk since context (which section you're in) disambiguates it in practice. I'd lean toward swapping `ready_to_publish`'s 🟢 for something outside the severity palette (e.g. 📤) — small change, closes a real if minor confusion.

---

## Appendix — actual generated messages (live, 2026-08-10 ~09:08 AEST)

### Morning Brief
```
☀️ MORNING BRIEF — Monday 10 August 2026
Stardate 2026.222 · 09:08 AEST

⚡ CAPACITY
  ███░░░░░░░ Recovery confidence 33%
  Energy Moderate · NS Dysregulated · Body Present

📡 INTELLIGENCE (24h)
  🔴 Armed officers to bolster security at Melbourne hospitals under opposition proposal
  🔴 Greens draw betting perk line ahead of gambling showdown
  🟢 AI fluency: The next foundation of US economic competitiveness
  🟢 Author Talks: One size does not fit all

🛰 PLATFORM HEALTH
  ⚠️ Captain, two platform domains are degraded.

The 'Insight Outcomes' data source has never reported a successful heartbeat, meaning its status is unconfirmed. The 'Morning Brief Push' job has also never reported, so its operational status is unknown.

These are known monitoring gaps with unconfirmed real impact.

✍️ CONTENT REVIEW (4)
  📝 ADHD Work Systems - how do Neuro Spicy Employees work better with work insturctions, pr…  [review · personal operating systems · today]
  📝 The Telstra outage is a stark reminder of the widespread effects of single-system failures  [ready_to_publish · operational resilience · 4 weeks old]
  📝 The power of data from Businss Impact Assesments if used correctly - hot spots in your …  [review · — · 5 weeks old]
  📝 Critical Infrastructure Resilience Management Plan (CIRMP) alignment.  [review · operational resilience · 5 weeks old]

🤖 XO · Starship Endeavour
```

### EOD Summary
```
🌙 END-OF-DAY SUMMARY — Monday 10 August
09:08 AEST

🔋 RECOVERY PULSES
  ███░░░░░░░ 33%  ·  ✅ ❌ ❌
  AM · Mid · PM
  NS Dysregulated · Body Present

🛰 PLATFORM HEALTH
  ⚠️ Captain, two platform domains are degraded.

The 'Insight Outcomes' data source has never reported a heartbeat, so its real-time status is unconfirmed. The 'Morning Brief Push' internal job has also never reported, so we cannot confirm if it is running.

Worth checking why these heartbeats were never wired in.

✍️ CONTENT REVIEW (4) (unchanged since this morning)
  📝 ADHD Work Systems - how do Neuro Spicy Employees work better with work insturctions, pr…  [review · personal operating systems · today]
  📝 The Telstra outage is a stark reminder of the widespread effects of single-system failures  [ready_to_publish · operational resilience · 4 weeks old]
  📝 The power of data from Businss Impact Assesments if used correctly - hot spots in your …  [review · — · 5 weeks old]
  📝 Critical Infrastructure Resilience Management Plan (CIRMP) alignment.  [review · operational resilience · 5 weeks old]

📝 LOG YOUR DAY
  Reply /log to record today's reflection

🤖 XO · Starship Endeavour
```

### Weekly Report
```
📊 WEEKLY INTELLIGENCE REPORT
04 Aug – 10 Aug 2026

🛰 TECH OSINT — WEEKLY (590)
  This week's OSINT is heavily dominated by Cloudflare Status reports, indicating widespread, high-confidence technical issues across their services, including network performance problems in various global locations and specific functionality failures like Workers, R2, and Gateway. Beyond these operational concerns, there are isolated reports of botnet activity targeting diagnostic tools and an npm worm, alongside general discussions around AI adoption and its impact from sources like McKinsey and MIT Sloan.
  🔴 16 high  ·  🟡 9 medium  ·  🟢 211 low  ·  ⚪ 354 unscored

🩺 HEALTH OSINT — WEEKLY (322)
  This week's health intelligence highlights a strong focus on ongoing clinical trials, particularly those sourced from ClinicalTrials.gov, covering a wide array of domains. Notable recurring themes include numerous studies on vaccine development and efficacy, especially for influenza and various infectious diseases, alongside a significant number of trials investigating new treatments for conditions like cancer and cardiovascular issues. There is also a consistent interest in mental health interventions and performance optimization, often involving exercise or behavioral strategies, and a steady stream of research into the potential benefits of various supplements.
  🔴 3 high  ·  🟡 149 medium  ·  🟢 170 low

✍️ CONTENT THIS WEEK (6)
  2 published  ·  3 review  ·  1 ready to publish
  ✅ Resilience by Design.  [published · operational resilience]
  ✅ McGill Method Physiotherapy Investigations  [published · —]
  📝 ADHD Work Systems - how do Neuro Spicy Employees work better with work insturctions, pr…  [review · personal operating systems]
  🟢 The Telstra outage is a stark reminder of the widespread effects of single-system failures  [ready_to_publish · operational resilience]
  📝 The power of data from Businss Impact Assesments if used correctly - hot spots in your …  [review · —]
  📝 Critical Infrastructure Resilience Management Plan (CIRMP) alignment.  [review · operational resilience]

⚡ CAPACITY THIS WEEK
  No capacity logs this week.

🤖 XO · Starship Endeavour
```

### Live queries backing §2 (Supabase project `cjvrpjwewsrumnbdydgg`)
- `captains_log_entries`: 6 rows total, most recent `log_date = 2026-06-28`.
- `recovery_pulses` last 7 days: 1 row (2026-08-10 morning pulse only). Last 14 days: singles on 07-27, 07-23, 07-18, 07-15, then today.
- `captain_readiness_history`: frozen at identical values (readiness_score=85, capacity_score=75) from 2026-07-10 through 2026-07-19, no rows after.
- `decision_records`: 31 rows, most recent `decision_timestamp = 2026-06-14`.
- `human_systems_recommendations`: most recent `issued_on = 2026-06-28`.
- Outage-alert-qualifying `intelligence_events` (`event_type IN (technology_outage, telecom_outage) AND customer_impact='high' AND confidence>=0.65`), last 7 days: 4 rows (listed in §2b).
- `intelligence_events` last 7 days: 592 rows total, `osint_confidence_level`: 356 NULL / 211 LOW / 16 HIGH / 9 MEDIUM.
- `health_signals` last 7 days: 322 rows, `confidence_level`: 0 NULL / 170 LOW / 149 MEDIUM / 3 HIGH.
- `verification_state` latest row: `state='unsure'`, `degraded_domains=[insight_outcomes, morning_brief]` — matches both live brief outputs exactly.
