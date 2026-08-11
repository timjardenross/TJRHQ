# Weekly Report: Decisions section removed + LLM exec summaries added

Commit: `d88cc1b0` (pushed to `main`)
File: `intelligence/captains_brief.py`

## What changed

### 1. Removed "DECISIONS THIS WEEK"

- Deleted `_get_weekly_decisions()` (the `decision_records` query) and
  `_format_weekly_decisions_block()` — no dead code path left, both functions
  had no other callers anywhere in the repo (verified with a repo-wide grep).
- Removed the two call sites from `generate_weekly_report()`.
- Updated the module docstring (line 7) and `generate_weekly_report()`'s own
  docstring to record why: `decision_records` is a stale/broken pipeline
  (being fixed separately) that was always rendering "No decisions logged
  this week" — removed rather than continue shipping a dead section.

### 2. Added two separate LLM exec summaries (Tech OSINT + Health OSINT)

Built the same way `core/platform/infra_narrative.py` builds its narrative:
reuses the exact same shared provider chain
(`core/llm/provider_chain.py`'s `call_gemini` → `call_mistral` →
`call_ollama`), same try-each-in-order / never-raise contract, same
guarded import pattern (`try/except` at module load, degrades to `None` if
the import itself fails).

- `_TECH_OSINT_SUMMARY_SYSTEM_PROMPT` / `_HEALTH_OSINT_SUMMARY_SYSTEM_PROMPT`
  — two distinct system prompts, each domain-specific, each carrying the
  same "no invented causes, only use what's provided" discipline as
  `infra_narrative.py`'s prompt, adapted per domain (no invented threats/
  causes for Tech, no invented study findings/causal claims for Health).
  Each asks for 2-4 tight sentences, Telegram-appropriate length, no
  markdown.
- `_call_weekly_summary_providers()` — the shared provider-chain caller,
  mirroring `infra_narrative.py`'s `_generate()`.
- `_generate_tech_osint_summary()` / `_generate_health_osint_summary()` —
  build the prompt from real query-result data (title, severity, sector or
  health_domain, source) for up to 40 highest-ranked rows, not just the
  bucket counts. Real source names are now fetched too — extended
  `_get_weekly_tech_signals()` / `_get_weekly_health_signals()`'s `select=`
  to embed `intelligence_source_registry(source_name)` /
  `health_source_registry(source_name)`, matching the join each workbench's
  own Intelligence Summary route already uses.
- `_format_weekly_osint_block()` now takes an optional `summary` param.
  When present, it's placed directly under the domain header, with the
  severity-count line kept right below it (fast-scan signal preserved).
  When absent (LLM unavailable or every provider failed on this run), the
  original raw severity-count + top-3-items display renders unchanged —
  verified this fallback path directly by forcing all three providers to
  raise and confirming no exception propagates and the raw display renders.
- `_truncate_clean(summary, 700)` kept as the safety-net truncation (same
  700-char limit `infra_narrative.py` uses), not the primary length control
  — the prompt itself asks for Telegram-appropriate length. First pass used
  a 500-char cap and it cut a live Gemini response mid-sentence; raised to
  700 after checking the raw (untruncated) response length and confirming
  700 covers a normal 2-4 sentence response without cutting it off.

## Verification performed

- `python3 -m py_compile intelligence/captains_brief.py` — clean.
- Generated the real weekly report against live Supabase data (env sourced
  from `telegram-bots/xo/.env`, per instruction) and read the full output.
  Both summaries generated via `gemini-2.5-flash` (the root `.env`'s
  `GEMINI_API_KEY`/`MISTRAL_API_KEY` get pulled into the process env as a
  side effect of `core/platform/heartbeat.py`'s `_load_dotenv()`, which runs
  at import time via the existing `infra_narrative` import chain — this is
  pre-existing behavior, not something this change introduced).
- Separately forced all three providers (`call_gemini`/`call_mistral`/
  `call_ollama`) to raise, confirmed `_generate_tech_osint_summary()` returns
  `None` without raising and `_format_weekly_osint_block()` renders the
  original raw-counts + top-items fallback.
- No live Telegram push was sent — output was printed/inspected only, per
  instruction.

## Sample of actual generated output (04 Aug – 10 Aug 2026 window)

```
<b>📊 WEEKLY INTELLIGENCE REPORT</b>
<i>04 Aug – 10 Aug 2026</i>

<b>🛰 TECH OSINT — WEEKLY (590)</b>
  This week's OSINT is dominated by high-confidence reports from Cloudflare Status detailing widespread technology sector issues, including network performance problems in various global locations, R2 and Workers availability issues, and configuration errors. Separately, the SANS Internet Storm Center reports on botnet activity targeting diagnostic tool vulnerabilities and an npm worm. Beyond these, there are scattered reports across financial services and general sectors, though these lack specific technical detail or confidence levels.
  🔴 16 high  ·  🟡 9 medium  ·  🟢 211 low  ·  ⚪ 354 unscored

<b>🩺 HEALTH OSINT — WEEKLY (322)</b>
  This week's health intelligence signals show a strong focus on ongoing clinical trials, particularly those sourced from ClinicalTrials.gov, covering a wide range of domains. There is a notable emphasis on vaccine development and efficacy, with a high-confidence report confirming the effectiveness of an updated mRNA booster, alongside several trials for various other vaccines. Research into mental health interventions and performance optimization, often in older adults or specific populations, also features prominently. Additionally, several trials are exploring the impact of various supplements and new treatments for conditions like cancer.
  🔴 3 high  ·  🟡 149 medium  ·  🟢 170 low

<b>✍️ CONTENT THIS WEEK (6)</b>
  2 published  ·  3 review  ·  1 ready to publish
  ✅ <b>Resilience by Design.</b>  [published · operational resilience]
  ✅ <b>McGill Method Physiotherapy Investigations</b>  [published · —]
  📝 <b>ADHD Work Systems - how do Neuro Spicy Employees work better with work insturctions, pr…</b>  [review · personal operating systems]
  🟢 <b>The Telstra outage is a stark reminder of the widespread effects of single-system failures</b>  [ready_to_publish · operational resilience]
  📝 <b>The power of data from Businss Impact Assesments if used correctly - hot spots in your …</b>  [review · —]
  📝 <b>Critical Infrastructure Resilience Management Plan (CIRMP) alignment.</b>  [review · operational resilience]

<b>⚡ CAPACITY THIS WEEK</b>
  No capacity logs this week.

🤖 <i>XO · Starship Endeavour</i>
```

Total length: 2268 chars (well under Telegram's 4096 cap). No `DECISIONS
THIS WEEK` section present. No `Missions` section (unchanged from the prior
2026-08-10 redesign — deliberate, per Captain's earlier direction).

## Notes / open items for the Captain

- `decision_records` pipeline fix is out of scope here and remains a
  separate, still-open item — this only removes the always-empty section
  from the weekly report.
- `CAPACITY THIS WEEK` showed "No capacity logs this week" in this test run
  — unrelated to this change, pre-existing behavior, not touched.
- In production the `xo` Telegram bot's own `.env` doesn't carry
  `GEMINI_API_KEY`/`MISTRAL_API_KEY` directly — those come from the root
  `.env` via `heartbeat.py`'s side-effecting `_load_dotenv()` at import time.
  This is pre-existing, shared by `infra_narrative.py` already, and not
  something introduced by this change, but worth knowing if the exec
  summaries ever mysteriously fall back to Ollama in an environment where
  that import chain doesn't fire.
