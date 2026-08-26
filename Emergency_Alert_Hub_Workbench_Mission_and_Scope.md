# Emergency Alert Hub Workbench — Mission & Scope

Source brief: `emergency_alert_hub_mission_product_scope.docx` (repo root, "Tier 1 Emergency Alert Hub — Technical build scope for Claude Code on a VM").
This document reframes that brief as a **new lcars-portal workbench**, composed on top of platform capabilities that already exist rather than a standalone VM app, per [[composition-first-design-principle]].

## 1. Mission (unchanged from source brief)

Aggregate **official Tier 1 emergency alerts only** (AU state/territory/national gov + emergency-management sources) into one authoritative, low-maintenance stream with full source traceability. No Tier 2/3, no social/news/unofficial aggregators.

## 2. Composition-first finding: this is ~70% already built

The original brief specs a standalone VM app (Node.js, own SQLite, own crawler, own admin console) as if starting from zero. It isn't zero. This platform already runs a structurally identical pipeline for a harder version of the same problem — tiered official sources → fetch → normalize → dedupe → rank → health-monitor → serve — for the ORI intelligence platform and Health OSINT. Reuse map:

| Brief's ask | Existing platform capability | Verdict |
|---|---|---|
| Tier 1/2/3 source classification | `intelligence/classification/source_tier.py` — deterministic domain→tier classifier, AU-focused, already lists `bom.gov.au`, `homeaffairs.gov.au`, `cyber.gov.au` etc. as Tier 1 | **Reuse + extend** with state emergency-services domains (rfs.nsw.gov.au, ses.vic.gov.au, dfes.wa.gov.au, etc.) |
| Explicit source allowlist keyed by jurisdiction/type | `intelligence_source_registry` pattern (migration 0004) — `jurisdiction`, `category`, `source_type` (rss/api/scrape/manual), `active`, `confidence_weight` | **Reuse the pattern**, new dedicated table (see §4 — field mismatch, not a fork of the concept) |
| RSS/JSON/Atom-first fetch, HTML crawl as fallback | `intelligence/ingestion/scrape_adapter.py`, `firecrawl_client.py` (Firecrawl REST, budget-capped), `downdetector_adapter.py` (per-source scrape, exact "official page, no API" pattern) | **Reuse directly** — same adapters, new source list |
| Per-domain rate limiting, conservative concurrency | `intelligence/ingestion/external_fetch_budget.py` — DB-backed hard cap circuit breaker, already enforced on the Firecrawl/Bright Data paths | **Reuse directly** |
| Schema-first parsers per source | `tools/health-osint/parsers/*.py` (one file per source, e.g. `parse_who_alerts.py`) — proven pattern for exactly this shape of work | **Reuse pattern**, one new parser per state source |
| Recheck active alerts more often than quiet sources | `downdetector_adapter.py`'s learned/tiered cadence + `domain_registry.expected_cadence_minutes`/`grace_period_minutes` | **Reuse directly** |
| Source health: last success, last failure, crawl status | `domain_registry` + `domain_heartbeats` + `domain_heartbeat_latest` view (migration 0071) + **Agent/Job dashboard** (`agent-status-workbench`, already live) | **Reuse directly, zero new UI** — register each state source as a `domain_key`; it shows up on the existing dashboard for free |
| Admin enable/disable, retry, run-now | `domain_registry.active` soft-delete convention already used platform-wide (migrations 0112/0117/0170) | **Reuse pattern** for a lightweight admin toggle; no new admin console needed |
| Dedup by canonical URL / event key | `intelligence_events.dedup_hash` (SHA-256 of title+source+date) + `canonical_url` | **Reuse pattern** |
| Curated, gated presentation (not raw feed dump) | Health OSINT's curation companion (`health-osint-curation` page + `health_signal_curation.py`) — exact precedent for "don't just dump the raw feed, gate it" | **Reuse pattern** |
| One hub page: table, jurisdiction filter, severity filter, status | Existing workbench shell/filter components (`lcars-portal/src/app/health-osint`, `weekly-review/_components/SignalRow.tsx` style rows) | **Reuse components**, new page |

Net: no new crawler engine, no new fetch-budget/rate-limit system, no new source-health mechanism, no new admin console mechanism, no new VM/deploy shape. Genuinely new work is the AU state-jurisdiction source list, one parser per source, one new canonical `alerts` table + API, and one new workbench page.

## 3. Why NOT reuse `intelligence_events` / `intelligence_source_registry` directly

Considered and rejected — these tables are shaped for the ORI *resilience-brief* product (banking/CPS230 relevance scoring, brief-inclusion linkage, rank_score for a curated top-5), not a public alert feed with its own lifecycle:

- `jurisdiction` is constrained to `AU/APAC/GLOBAL` — the brief needs state-level (NSW/VIC/QLD/WA/SA/TAS/NT/ACT).
- No `severity`, `expiry`, `status`/`is_active`, or `event_key` columns — alerts need an explicit active→superseded/expired→inactive state machine; intelligence_events has no such lifecycle (it's collect-once, brief-or-archive).
- `banking_relevance`, `cps230_relevance`, `dependency_risk` are meaningless for a bushfire warning and would sit permanently null — schema noise, not reuse.

Per [[suoc-universal-concept-duplication]], bolting a second, incompatible schema onto a shared table is worse than a small dedicated schema that follows the *same proven pattern* (registry + health + canonical record + RLS, per migration 0004 and 0071's own conventions). New tables, same discipline:

- `alert_sources` (mirrors `intelligence_source_registry`, jurisdiction = AU state/territory/national)
- `alerts` (canonical record: source, jurisdiction, alert_type, severity, headline, description, location, issued_at/updated_at/expiry, status, is_active, canonical_url, raw_text, event_key)
- Fetch/crawl logging: **no new table** — reuse `domain_heartbeats` by registering each source as a `domain_registry` row (category=`data`, one row per state source or one per jurisdiction bundle)

## 4. Firecrawl budget risk — flagged, not yet resolved

`FIRECRAWL_API_KEY` is capped at 1,000 scrapes/month platform-wide, shared with ORI/Health OSINT/Downdetector (`external_fetch_budget.py` enforces this). Most Tier 1 AU state sources (NSW RFS, VicEmergency, QFES, DFES, SES) publish RSS/JSON/API feeds — those should go through the existing `scrape_adapter.py`/plain-fetch path, **not** Firecrawl, and cost nothing against that budget. Firecrawl should only be the fallback for sources confirmed to sit behind a JS-challenge/WAF (same bar `firecrawl_client.py`'s docstring already sets). Needs a per-source audit before build: which of the 8 jurisdictions' primary surfaces are real feeds vs. JS-rendered pages.

## 5. Proposed scope (workbench, not standalone VM app)

**New:**
- Migration: `alert_sources`, `alerts` tables (RLS matching the 0004/0071 read-open/service-write convention) + `domain_registry` rows for each source's heartbeat
- `intelligence/ingestion/emergency_alert_adapters/` — one parser per jurisdiction primary surface (8-10 files), same shape as `tools/health-osint/parsers/`
- One normalizer module: source payload → canonical `alerts` row, dedupe by `canonical_url` then `event_key`
- One scheduler entry in `intelligence/scheduler.py` (reuse the existing scheduler process, not a new one) — active-alert refresh cadence tighter than quiet-source cadence, same tiering `downdetector_adapter.py` already does
- `lcars-portal/src/app/emergency-alert-hub/` — new workbench page: alert table, jurisdiction filter, severity filter, active/inactive toggle, detail panel (raw text + source link). Source health: **link to the existing Agent/Job dashboard filtered to these domain_keys**, not a rebuilt panel.
- API routes: `GET /api/emergency-alerts`, `GET /api/emergency-alerts/sources` (thin, same shape as existing `/api/agent-status`)

**Explicitly out of scope for v1** (per brief's own "optional" note and to keep this shippable):
- Notification/webhook/email layer — brief marks this optional; `core/command-centre/backend/services/notification-engine.js` already exists as the platform's live notification engine and is the natural home if/when this is wanted, not a new bespoke sender (per [[suoc-universal-concept-duplication]] — 5+ notification senders already exist, do not add a 6th)
- PDF/OCR advisory ingestion (brief allows it only as a fallback; skip until a real source needs it)

## 6. Open questions for Captain sign-off before build

1. Confirm the 8 jurisdiction "primary alert surfaces" in the brief's inventory table are still current (some state sites change layout without notice — same failure class `intelligence_source_registry` sources already hit).
2. Confirm reusing `agent-status-workbench` for source health is acceptable instead of the brief's own bespoke "source health view" — same information, zero duplicate UI, consistent with the just-shipped Platform Health P1-only change (don't build a second alarming dashboard).
3. New workbench nav slot — where does this sit in the LCARS Portal nav (own top-level workbench vs. folded into Intelligence Workbench as a filtered view)?

## 7. Not started

This is scope only. No migration applied, no code written. Awaiting Captain go-ahead on §6 before implementation.
