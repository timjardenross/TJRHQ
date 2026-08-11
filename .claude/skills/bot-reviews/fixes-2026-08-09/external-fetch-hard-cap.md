---
title: External fetch-path hard-cap circuit breaker (Firecrawl + Bright Data)
date: 2026-08-10
author: Chief Engineer (Claude Sonnet 5)
status: DELIVERED — code complete, live-verified with one real call per provider
mission: Captain-directed follow-up to the same night's firecrawl-production-provisioning.md
  and brightdata-provisioning.md. Both fetch paths were sized against their
  real monthly quota by MATH (projected call volume vs. known cap), not by
  anything that actually stops a call once a safe ceiling is reached. The
  Captain asked for a real, enforced hard cap — one that refuses further
  calls regardless of what changes to cadence/source count happen later
  (new sources added, a cron misconfiguration, a retry-loop bug, etc.).
---

# Mission Summary

Built a shared, DB-backed hard-cap circuit breaker (`intelligence/ingestion/
external_fetch_budget.py`) and wired it into both paid external fetch-path
clients — `firecrawl_client.py` and `brightdata_fetch.py` — so every real
outbound call to either provider is atomically checked against a safe
ceiling for the current billing cycle *before* it fires, and refused
(loudly logged, never silently swallowed) once that ceiling is reached.
This replaces "sized by math" with "enforced by code."

# What was built

## 1. Usage table + atomic RPC (migration, project `cjvrpjwewsrumnbdydgg`)

No existing table covered this (checked `intelligence_source_registry` and
`llm_cost_governance` first — neither tracks external-API call volume by
provider/cycle). New table:

```sql
external_fetch_usage (
  provider            text,
  billing_cycle_start date,
  billing_cycle_end   date,
  call_count          integer,
  updated_at          timestamptz,
  created_at          timestamptz,
  primary key (provider, billing_cycle_start)
)
```

One row per (provider, billing_cycle_start) — a fresh row per real billing
cycle, so past cycles stay as an audit trail rather than being overwritten.
RLS enabled, no policies (same "service_role bypasses, nothing else gets
in" pattern already used by `llm_cost_governance`/`llm_call_metrics` in this
schema).

Check-and-increment is a single atomic Postgres function,
`external_fetch_try_increment(p_provider, p_billing_cycle_start,
p_billing_cycle_end, p_ceiling)`, `SECURITY DEFINER`, row-locked (`SELECT
... FOR UPDATE`) so two concurrent callers for the same provider+cycle can
never both read "under ceiling" and both proceed — this matters concretely
because Firecrawl's own client already runs a 2-concurrent-request
semaphore, i.e. real concurrent callers are a live scenario, not a
theoretical one. Granted to `service_role` only.

**A real bug was caught by live testing, not just review**: the function's
first version used `RETURN QUERY select false, v_count;` to signal a
refusal, but `RETURN QUERY` does not exit a PL/pgSQL function — execution
fell through to the `UPDATE` below regardless, so the *stored* call_count
kept climbing on every refused call even though the correctly-shaped first
response row still said `allowed: false` (confirmed live: 3 calls allowed
against a test ceiling of 3, then 2 more calls both correctly refused from
the caller's perspective, but the stored counter had silently climbed to 5,
not stayed at 3). Fixed with an explicit `RETURN;` immediately after the
refusal branch. This was live-tested, caught, and fixed within this
mission — not shipped and left for later.

## 2. Shared Python module: `intelligence/ingestion/external_fetch_budget.py`

- `PROVIDERS` config: `firecrawl` (cap 1,000, ceiling **850**, cycle anchor
  day 9) and `brightdata` (cap 5,000, ceiling **4,500**, cycle anchor day
  1).
- `_cycle_bounds(today, anchor_day)` — computes each provider's real,
  non-calendar-aligned billing cycle from its actual anchor day (see
  §4 below), not a generic "resets on the 1st" assumption.
- `check_and_increment(provider)` — the gate. Must be called immediately
  before the real outbound HTTP request. Raises `FetchBudgetExceeded` if
  the ceiling would be reached/exceeded, or `FetchBudgetCheckFailed` if the
  check itself couldn't complete (Supabase unreachable, credentials
  missing, malformed RPC response). Both are `RuntimeError` subclasses.
- `current_usage(provider)` — read-only lookup for the checker tool below;
  never guesses (raises rather than reporting a fabricated "0 used" if the
  real count can't be read).

## 3. Wiring into both clients

`firecrawl_client.scrape()` and `brightdata_fetch.fetch_html()` each call
`external_fetch_budget.check_and_increment(provider)` as their first
action after the "is the API key configured" check, before constructing
the real HTTP request. The exception is **not** caught locally — it
propagates up to the calling adapter (`DowndetectorAdapter._fetch_html`,
`ScrapeAdapter` for AEMO/Fastly), which already has no local catch for
fetch failures. That's fine, and deliberate: the codebase already has a
two-layer safety net that this circuit breaker relies on rather than
duplicates:

1. `intelligence/ingestion/base_adapter.py`'s `BaseSourceAdapter.run()`
   wraps every `collect()` call in its own try/except — never raises,
   records `SourceHealth(status="failed", error_message=...)` and logs via
   `log.error`.
2. `intelligence/ingestion/collection_engine.py`'s `collect_all()` wraps
   each adapter's `.run()` future in its own try/except as an extra layer.

So a refused call degrades to exactly one source reporting a `failed`
health record for that run — the scheduler job itself never crashes, and
every other source's collection proceeds normally.

## 4. Billing-cycle rollover (provider-specific anchor day, not calendar-month)

- Firecrawl: cycle 2026-08-09 → 2026-09-09 (anchor day 9, confirmed via
  `firecrawl credit-usage`).
- Bright Data: cycle 2026-08-01 → 2026-09-01 (anchor day 1, inferred from
  "renews 01.09.26" — next reset 1 September 2026 implies the current
  cycle started 1 August 2026 on a monthly cadence).

`_cycle_bounds()` computes each cycle from `today` and the provider's own
anchor day (clamped to the real last day of a short month for anchor days
>28, though neither provider's anchor here needs that). Live-verified: the
usage checker tool (below) printed exactly `2026-08-09..2026-09-09` for
Firecrawl and `2026-08-01..2026-09-01` for Bright Data on 2026-08-10.

## 5. Failed-call billing verification (not assumed)

The task asked to verify, per provider, whether a failed call still
consumes quota rather than assuming it does. Researched rather than
guessed:

- **Firecrawl**: genuinely mixed signal. The vendor's own docs claim
  failed requests aren't billed; independently reported real-world
  experience says mid-request failures (timeouts, render errors) can still
  consume a credit. Not a confirmed "failures are free" guarantee.
- **Bright Data Web Unlocker**: clearer — default billing is
  success-only, *except* that enabling any Custom Web Unlocker API feature
  (custom headers/cookies/expect-elements) flips billing to 100% of
  requests, success or failure. `brightdata_fetch.py` doesn't currently
  enable those features, so today's real usage is likely success-only
  billed — but that's a zone-config detail this module has no visibility
  into and that could change without a code change here.

Given that ambiguity, the circuit breaker counts **every real outbound
attempt** for both providers uniformly, regardless of outcome. This is
deliberately conservative: worst case it spends a little of the safety
margin baked into the ceiling faster than strictly necessary; it can never
let real spend outrun what's counted.

## 6. Fail-safe, not fail-open

`core/platform/infra_narrative.py`'s docstring states the principle this
mission was told to reuse: `generate_infra_narrative()` returns `None` on
any read failure, and "the caller ... treats `None` as 'omit this
section', never as evidence of a healthy platform." Applied here: if
`external_fetch_budget.py` cannot complete the atomic check-and-increment
(Supabase down, credentials missing, RPC error), it does **not** default
to "must be under budget, allow the call" — that would silently permit
exactly the quota blowout this circuit breaker exists to prevent. It
raises `FetchBudgetCheckFailed` instead, treated identically to a genuine
ceiling breach by both callers. This is a deliberate departure from this
same codebase's `llm_cost_governance.py`, which defaults to *permissive*
on a config/metrics read failure (documented in its own docstring) — that
default is reasonable for an internal soft cost estimate where the
downside of a miss is a slightly-too-high internal LLM bill; it is the
wrong default for a hard external vendor quota where the downside of a
miss is the account itself getting cut off or rate-limited mid-month.

## 7. Read-only usage checker: `tools/external_fetch_usage_check.py`

Same "check without mutating" pattern as `tools/registry_staleness_check.py`
and `tools/id_counter_drift_check.py`. Uses `current_usage()`, never
`check_and_increment()`.

```
$ python3 tools/external_fetch_usage_check.py
Provider    Cycle                   Used    Ceiling   RealCap  Headroom  %
brightdata  2026-08-01..2026-09-01  1       4500      5000     4499      0.0
firecrawl   2026-08-09..2026-09-09  1       850       1000     849       0.1
```

Exit code 0 if every checked provider is under ceiling and readable, 1 if
any provider is at/over ceiling or its usage couldn't be read.

# Verification performed

1. `python3 -m py_compile` clean on all four touched/new files
   (`external_fetch_budget.py`, `firecrawl_client.py`, `brightdata_fetch.py`,
   `tools/external_fetch_usage_check.py`).
2. **Simulated ceiling test** (no real API credits spent — HTTP layer
   mocked): a throwaway `test_provider_circuit_breaker_verify` provider
   with `ceiling=3` was driven through 5 real DB-backed
   `check_and_increment()` calls. Calls 1–3 correctly allowed
   (count 1, 2, 3); calls 4–5 correctly refused with
   `FetchBudgetExceeded`, and — after the `RETURN;` fix — the stored
   `call_count` correctly stayed at exactly 3, not climbing past the
   ceiling. `current_usage()`'s independent read agreed (3/3, headroom 0).
   Row cleaned up afterward.
3. **Gate-before-network test**: `check_and_increment` mocked to raise;
   `urllib.request.urlopen` mocked to raise `AssertionError` if ever
   called. Both `firecrawl_client.scrape()` and
   `brightdata_fetch.fetch_html()` raised `FetchBudgetExceeded` without
   ever reaching the network layer.
4. **Below-ceiling pass-through test**: `check_and_increment` mocked to
   allow; `urllib.request.urlopen` mocked to return a fake successful
   response. Confirmed `scrape()` proceeds to exactly one (mocked) HTTP
   call.
5. **One real live call per provider** (real credits spent, by design —
   the mission required this): `firecrawl_client.scrape('https://
   example.com')` and `brightdata_fetch.fetch_html('https://example.com')`
   both succeeded end-to-end through the real gate against the real
   Supabase-backed counters. Verified via `tools/
   external_fetch_usage_check.py` immediately after: both providers'
   `call_count` read back as exactly `1`, cycle boundaries correct.
6. Grepped every new/touched file against the real `FIRECRAWL_API_KEY` /
   `BRIGHTDATA_API_KEY` values from `.env` before committing — no leaks
   (a prior mission tonight had leaked the Firecrawl key value into a
   committed doc; this mission does not repeat that).

# Files touched

- `intelligence/ingestion/external_fetch_budget.py` (new) — the shared
  circuit breaker.
- `intelligence/ingestion/firecrawl_client.py` — gate wired into
  `scrape()`; docstring updated.
- `intelligence/ingestion/brightdata_fetch.py` — gate wired into
  `fetch_html()`; docstring updated.
- `tools/external_fetch_usage_check.py` (new) — read-only usage/headroom
  checker.
- Supabase migrations (project `cjvrpjwewsrumnbdydgg`):
  `external_fetch_usage_hard_cap`,
  `external_fetch_try_increment_fix_ambiguous_column_v2`,
  `external_fetch_try_increment_fix_missing_return` (the second and third
  are same-session fixes for real bugs caught during live testing, see §1
  and §6 above — not left in the migration history unexplained).

# Ceilings, one more time for clarity

| Provider | Real vendor cap | Enforced ceiling | Margin | Billing cycle (as of 2026-08-10) |
|---|---|---|---|---|
| Firecrawl | 1,000/month | **850** | 85% (150 credits headroom) | 2026-08-09 → 2026-09-09 |
| Bright Data | 5,000/month | **4,500** | 90% (500 credits headroom) | 2026-08-01 → 2026-09-01 |

Firecrawl gets a slightly larger safety margin because that account is
shared with the Captain's own ad hoc interactive `firecrawl` CLI use, which
this module has no visibility into; Bright Data's account is dedicated
entirely to this pipeline.

# Mission Status

Delivered. Circuit breaker is live and enforcing on both providers as of
this commit — the next real call to either provider (from the normal
scheduled collection jobs) will be gated by this code, not just by cadence
math. No further Captain action needed to activate; this composes with the
already-live Firecrawl/Bright Data fetch paths without changing their
external behavior below the ceiling.

One open item, not built here (out of scope for a hard-cap circuit
breaker): no alerting/notification fires when a provider approaches or
hits its ceiling beyond the `journalctl`-visible `log.warning`/`log.error`
lines — a human (or a future mission) needs to either watch logs or run
`tools/external_fetch_usage_check.py` to notice. Flagged, not silently
left for someone to discover the hard way.
