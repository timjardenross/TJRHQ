# XO Telegram Review Follow-ups — 2026-08-10

Fixes for the 3 confirmed findings in `xo-telegram-review.md` (XO's product review of the 2026-08-09/10 Telegram brief rework). All 3 fixed, verified against live data, committed separately, pushed.

Commits (on `main`, in order):
1. `f641072e` — weekly Capacity fallback
2. `49239646` — content-status icon collision
3. `f555355c` — outage-push-alert classifier guard

---

## 1. Weekly Capacity block dead on arrival — FIXED

**Root cause:** `_get_weekly_capacity()` in `intelligence/captains_brief.py` queried only `captains_log_entries`, which has had no new rows since 2026-06-28. Unlike Morning/EOD (`_get_todays_health()` / `_get_recovery_status()`, which already fall back to `recovery_pulses` / `recovery_confidence_today`), the weekly path had no fallback and always rendered "No capacity logs this week."

**Fix:** `_get_weekly_capacity()` now falls back to `recovery_pulses` over the 7-day window when `captains_log_entries` is empty, returning `{"source": "log"|"pulse"|"none", "entries": [...]}`. `_format_weekly_capacity_block()` renders a recovery-confidence-style summary (pulses logged, days covered, latest energy/nervous-system/body signals) for the pulse-sourced case, matching the Morning/EOD fallback pattern.

**Live verification** (generated `generate_weekly_report()` against live Supabase, project `cjvrpjwewsrumnbdydgg`):
```
⚡ CAPACITY THIS WEEK
  ░░░░░░░░░░ Recovery confidence 5%  ·  1 pulse(s) logged across 1 day(s) (of 7)
  Latest: Energy Moderate · NS Dysregulated · Body Present
```
As anticipated in the review, current pulse-logging is sparse — the honest output is "1 pulse logged this week," a real (if uncomfortable) signal about logging adherence, not a bug. Confirmed the fix queries the right table and will surface real data if/when more pulses are logged.

---

## 2. Classifier misclassification on the outage-push trigger path — MITIGATED (not fixed at the classifier level — see reasoning)

**Confirmed root cause:** `intelligence/classification/classifier.py`'s `technology_outage` keyword rule list includes bare, generic terms — notably `"platform"` and vendor names like `"microsoft"` — that match any story mentioning a tech platform or company, not just outage reports. The 2026-08-04 story "Trump wants 'fair treatment' ... Labor's levy on tech giants" matched on `"platform"` ("big tech platforms") and `"microsoft"` ("Microsoft's LinkedIn"), scoring higher than every other category (its only other match, `"tariff"` under `geopolitical`, tied at 1 hit but `technology_outage` iterates first in `_EVENT_TYPE_RULES` and the loop uses strict `>`, so it kept the earlier winner). This produced `event_type=technology_outage, customer_impact=high, confidence=0.67` — enough to cross the outage-push threshold.

This is exactly the same bare-keyword substring-collision defect `classifier.py`'s own comments document being found and fixed for four *other* categories on 2026-07-18 (`payments_disruption`, `energy_disruption`, `severe_weather`, `transport_disruption`) — `technology_outage` itself was never audited for it.

**Why I didn't fix it at the classifier level:** I queried live data before touching the shared rule list and found the blast radius is much larger than this one story:
```sql
-- last 30 days, event_type = 'technology_outage'
total: 510
has a genuine incident-language keyword (outage/incident/degraded/...): 358
relies solely on generic terms (platform/aws/azure/microsoft/cloud/...): 152  (30%)
```
Sampling that 152 showed a mix of real (if oddly-worded) status-page items and a large amount of unrelated news (lawsuits, bankruptcies, celebrity news, regulatory stories) riding the same bare-keyword defect. Reworking `technology_outage`'s keyword list is a platform-wide classification change — it also drives the weekly OSINT roll-up counts and every other consumer of `event_type` — and deserves its own scoped review with broader sampling, not a same-night patch bundled with unrelated UI fixes. Per the mission's own guidance, this is exactly the case for a narrower mitigation rather than forcing a full fix.

**Mitigation implemented:** `intelligence/persistence/intelligence_store.py`'s `_maybe_push_outage_alert()` (the push-alert trigger, not the classifier) gained an additional gate, `_has_outage_language()`, requiring genuine incident-report language (`outage`, `incident`, `degrad`, `unavailable`, `unable to access`, `service disruption`, `system failure`, `service interruption`, `api failure`, `latency`, `error rate`, `elevated error`, `restored`, `resolved`, `mitigat`, `impacted`) in the event's own title/summary before pushing. This only affects the push path — the classifier, and every other consumer of `event_type`/`customer_impact` (weekly report, dashboards), is untouched.

**Live verification:**
- Fetched the exact live DB row for the misclassified event (`event_id=e23eec3b-...`) and ran it through the gating logic: would have pushed before the fix, does **not** push after.
- Ran the guard against all 40 push-eligible events (`technology_outage`/`telecom_outage`, `customer_impact=high`, `confidence>=0.65`) over the last 90 days: it excludes exactly 2 — the misclassified political story, and one Telstra opinion/commentary piece ("...is a result of prioritising neoliberal 'competition'...") published well after the actual outage, which is analysis *about* an outage rather than a report *of* one occurring (matching the review's suggested "story ABOUT vs. report OF" distinction). Every one of the other 38 genuine live-incident reports (Cloudflare, Salesforce, Oracle Cloud, Notion, Telstra outage news, Google Cloud, GitHub, Slack, Vercel-style status pages) still passes and would still push.

**Recommendation for a follow-up mission:** a dedicated pass over `classifier.py`'s `technology_outage`/`telecom_outage` keyword lists (same treatment as the 2026-07-18 fixes for the other 4 categories) — tightening or removing the bare `"platform"`/vendor-name keywords — would fix the underlying 30%-false-positive rate at the source rather than only at this one trigger point. Flagging, not actioning, per the "don't force a fix that risks breaking other things" instruction.

---

## 3. Icon collision (🟢/🟡 severity vs. content-status) — FIXED

**Root cause:** `_format_weekly_content_block()` in `intelligence/captains_brief.py` used `status_emoji = {"published": "✅", "ready_to_publish": "🟢", "approved": "🟡", "review": "📝"}` — reusing the exact glyphs `_SEVERITY_EMOJI` uses for "low/fine" (🟢) and "medium/caution" (🟡) a few lines above in the same weekly Telegram message, to mean workflow stage instead of severity. Same message, opposite meanings, two blocks apart.

**Fix:** `ready_to_publish` → 📤 (outbox — ready to act), `approved` → ☑️ (checked — approved), both now outside the 🔴🟡🟢⚪ severity vocabulary. `published` (✅) and `review` (📝) were already distinct and unchanged.

**Live verification:**
```
🛰 TECH OSINT — WEEKLY (592)
  ... 🔴 16 high · 🟡 9 medium · 🟢 211 low · ⚪ 356 unscored
...
✍️ CONTENT THIS WEEK (6)
  ... 📤 The Telstra outage is a stark reminder ...  [ready_to_publish · operational resilience]
```
🟢 now only ever appears meaning "low severity" in these briefs.

---

## Verification method (all 3)

- `python3 -m py_compile intelligence/captains_brief.py intelligence/persistence/intelligence_store.py` — clean.
- Generated `generate_morning_brief()`, `generate_eod_summary()`, and `generate_weekly_report()` live against Supabase project `cjvrpjwewsrumnbdydgg`, env sourced from `telegram-bots/xo/.env` — no mocking, no Telegram send. Morning/EOD unaffected (confirmed unchanged) and still render correctly; Weekly now shows the fixed Capacity block and icon.
- Finding #2 additionally verified by fetching the exact live offending row and replaying the actual gating logic, plus a 90-day sweep of every push-eligible event to confirm zero regressions on real outages.
