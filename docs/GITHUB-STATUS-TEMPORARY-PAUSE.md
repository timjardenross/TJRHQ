# GitHub Status: temporary collection pause (2026-11-24)

**Status:** paused, reversible. The source row, its history and the seed registry are untouched.

## Reason
GitHub Status incidents were judged noise in the briefs (see the 2026-11-02 note in `intelligence/captains_brief.py` and the
low-impact rule in `intelligence_store.py`). Collection is paused while that is resolved. The source is not retired.

## Mechanism
`intelligence.config.paused_source_names()` (default `{"GitHub Status"}`), applied in `collection_engine.collect_all()`,
so every job (daily, intraday, brief generation) skips it. Env override: `INTELLIGENCE_PAUSED_SOURCES`.
No DB write is needed. An optional, not-executed registry-level variant is `scripts/pause_github_status_20261124.sql`.

## Coverage limitation
No new GitHub Status events (api source, category `cloud_technology`). Existing events stay in the database and briefs.
GitHub outages still surface via the separate "GitHub Status (Uptime Kuma direct probe)" source (not paused), media
coverage and Downdetector-style signals; granularity and official incident wording are lost. No health record is written
for the paused source, so freshness audits may show it stale.

## Reinstatement criteria
Reinstate when briefs can drop or down-rank low-impact status incidents reliably, or the Captain asks for GitHub incident
coverage back (for example during a GitHub-dependent change window).

## How to reinstate
1. Set `INTELLIGENCE_PAUSED_SOURCES=none` in the `intelligence-scheduler` service environment and restart it, or
   empty `DEFAULT_PAUSED_SOURCE_NAMES` in `intelligence/config.py`.
2. If the SQL script was run, apply its documented reinstate statement.
3. Confirm the next sweep logs a `GitHub Status` health record.
