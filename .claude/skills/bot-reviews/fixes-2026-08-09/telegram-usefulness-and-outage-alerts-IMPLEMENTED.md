# Telegram Usefulness + Outage-Threshold Push — Implementation Report

**Implemented by:** Chief Engineer, USS-TJR-003, Engineering Division.
**Date:** 2026-08-09.
**Design doc:** `telegram-usefulness-and-outage-alerts-design.md` (same directory) — Captain-approved, both parts, as-specced.
**Authority note:** this is an implementation task under explicit Captain sign-off recorded in the design doc's header ("Requested by: Captain TJR... Full design doc... approved"). No further escalation required; Part 2's threshold was the exact value the design doc proposed and the Captain approved (`customer_impact='high' AND confidence>=0.65`), not re-derived here.

---

## Part 1 — message quality fixes (4 items)

### 1. Infra-narrative prompt now requires a stated action
**File:** `core/platform/infra_narrative.py`, `_SYSTEM_PROMPT` (around line 40).
Added to the end of the existing prompt string, exactly as designed:
> "Always end with one explicit line stating either what the Captain needs to do right now, or that this is already being monitored/handled automatically and needs no action."

No line-number drift from the design doc's citation — edited in place.

### 2. De-duplicated Content Review / Platform Health block generation
**File:** `intelligence/captains_brief.py`.
Extracted two shared helpers, both called from `generate_morning_brief()` and `generate_eod_summary()`:
- `_format_infra_block(infra, morning_text=None) -> list[str]`
- `_format_content_review_block(content_queue, morning_text=None) -> list[str]`

Added `_get_todays_morning_brief_text()` — a best-effort fetch of today's already-persisted morning brief text from `captains_daily_briefs` (order by `generated_at.desc`, `brief_date=eq.today`, `brief_type=eq.morning`). `generate_eod_summary()` fetches this once and passes it to both formatters.

**Same-day repeat marker:** as designed, this is a cheap substring/title-set comparison against the morning's persisted text, not a new structured-data path:
- Content Review: unchanged if every item's title is found verbatim inside the morning brief text → header gets `<i>(unchanged since this morning)</i>` appended, items still render (with age — see item 3) rather than being suppressed.
- Platform Health: unchanged if the (400-char-truncated) narrative string is found verbatim inside the morning brief text → same marker.

Caveat worth flagging: the Platform Health narrative is LLM-generated fresh on every call (via `generate_infra_narrative()`), so if the underlying degraded-domain set is identical but the LLM phrases the EOD narrative differently, the substring match will not fire and it will render as a "new" warning rather than "unchanged." This is an inherent limit of comparing rendered text rather than the underlying `verification_state` row (a scope choice made in the original design doc — "cheap to compute since `_persist_brief()` already stores the morning brief text"), not a bug in this implementation. Flagging it as a known limitation rather than silently accepting it.

### 3. Content Review item age now shown
**File:** `intelligence/captains_brief.py`.
Added `_relative_age(timestamp) -> str` (today / "N days old" / "N week(s) old" / "age unknown"), fed by the `draft_generated_at` field already selected in `_get_content_review_queue()`. Rendered inside `_format_content_review_block()` as a third bracketed field:
`📝 <b>{title}</b>  [{status} · {pillar} · {age}]`

### 4. Unified severity iconography
**File:** `intelligence/captains_brief.py`.
Replaced the three independent vocabularies (`_risk_emoji` 🔴🟡🟢⚪, `_priority_label` 🔥⚡📌📎, `_cap_emoji` 🟢🟡🔴) with one shared table, `_SEVERITY_EMOJI = {"red": "🔴", "yellow": "🟡", "green": "🟢", "none": "⚪"}`, accessed via `_severity_emoji(level)`. All three original functions kept their existing names/signatures (no caller changes needed elsewhere) but now delegate to the shared table:
- `_risk_emoji`: HIGH→red, MEDIUM→yellow, LOW→green, else→none.
- `_priority_label`: P0→red, P1→yellow, P2→green, P3→none (previously a 4th distinct icon set; now the same 4-symbol grammar risk/capacity already use).
- `_cap_emoji`: ≥70→green, ≥40→yellow, else→red (unchanged thresholds, same semantics — green=good throughout, direction differs by section but the *symbol set* is now single).

---

## Part 2 — outage-threshold push notification

**File:** `intelligence/persistence/intelligence_store.py`.

Added `_maybe_push_outage_alert(event: RankedEvent, event_id: Optional[str])`, called from `save_event()` immediately after the existing `_publish_core_event(...)` call, exactly at the location the design doc specified.

**Trigger condition (as approved, unchanged):**
```
event_type IN ('technology_outage', 'telecom_outage')
AND customer_impact == 'high'
AND confidence >= 0.65
```

**Wiring:** reuses `core.platform.notification_service.notify()` — no new sender. Same lazy-import-via-`sys.path` pattern already used by `_publish_core_event()` in the same file, for consistency. Severity: `Severity.ALERT` (matches the existing precedent in `interrupt_dispatcher.py`'s INTERRUPT_NOW push — `Severity.CRITICAL` is reserved elsewhere for the platform's own internal-failure alerts, e.g. the validation-suite regression job). Template: `"alert"`. Transport: `Transport.TELEGRAM`.

**Message content** (title, why it triggered, reference — per the design's spec):
- Title: `Outage — {event_type with underscores replaced by spaces}: {raw_title}`
- Body: `Triggered: customer_impact={value}, confidence={value:.2f}\nRef: {canonical_url, or event_id=... if no URL, or "no reference available" if neither}`

**Failure isolation:** the whole check is wrapped in try/except and only logs a warning on failure — never raises, never affects `save_event()`'s own persistence success/failure, matching every other post-persist side effect in this module.

### Verification performed
Ran a standalone smoke script (`intelligence.persistence.intelligence_store._maybe_push_outage_alert`, with `core.platform.notification_service` mocked out) covering:
1. A synthetic `technology_outage` event with `customer_impact='high'`, `confidence=0.70` → fires exactly once; body contains `customer_impact=high`, `confidence=0.70`, and the `canonical_url`; title contains the event's `raw_title`; severity/template/transport as specced.
2. Wrong `event_type` (e.g. `regulatory_change`) → does not fire.
3. `customer_impact='medium'` → does not fire.
4. `confidence=0.50` (below the 0.65 floor) → does not fire.
5. `telecom_outage` event type with no `canonical_url` → fires, body falls back to `event_id=...` as the reference.
6. `notify()` raising an exception internally → swallowed, logged, does not propagate (confirms the best-effort contract).

All six cases passed.

---

## Verification summary (both parts)

- `python3 -m py_compile` clean on all three changed files: `core/platform/infra_narrative.py`, `intelligence/captains_brief.py`, `intelligence/persistence/intelligence_store.py`.
- `core.platform.infra_narrative._SYSTEM_PROMPT` checked directly for the new required-action sentence.
- `intelligence.captains_brief` icon-unification functions (`_risk_emoji`, `_priority_label`, `_cap_emoji`) exercised directly against all input classes (HIGH/MEDIUM/LOW/unknown, P0-P3/unknown, numeric thresholds/non-numeric) — confirmed single 🔴🟡🟢⚪ vocabulary throughout.
- `_relative_age()` exercised across today / 1 day / 5 days / 28 days (both `Z`-suffixed and `+00:00`-suffixed ISO timestamps) / `None`.
- `_format_content_review_block()` and `_format_infra_block()` exercised standalone: age rendering, "unchanged since this morning" marker firing when content matches a supplied `morning_text`, and correctly *not* firing when content differs.
- Full end-to-end smoke test with mocked Supabase fetchers: called `generate_morning_brief()` and `generate_eod_summary()` back-to-back with the EOD run's `_get_todays_morning_brief_text()` returning the morning run's actual output text — confirmed both the Platform Health and Content Review sections in the EOD output correctly render `(unchanged since this morning)` while the morning output does not.
- Also ran `generate_morning_brief()` / `generate_eod_summary()` with no Supabase credentials configured (this sandbox has none) to confirm the refactor doesn't introduce new failure modes when every fetcher legitimately degrades to empty — both generators still produce valid Telegram-formatted text with no exceptions.

## Deviations from the design doc

None. All file paths, function names, and the exact threshold value matched what the design doc specified; no cited line numbers had drifted enough to require adaptation. Items scoped as P3/backlog in the design doc (word-boundary truncation, stale-decisions surfacing) were intentionally **not** implemented — they were explicitly out of scope for this mission (only the 4 named Part 1 items + Part 2 were commissioned).

## Mission status

Implementation complete for both parts, as specced. Committed and pushed in per-part commits (see git log). No new database migrations required — Part 2 reuses existing `intelligence_events` columns and the existing `notification_service.notify()` sender; Part 1's "unchanged" detection reuses the existing `captains_daily_briefs` table with no schema change.
