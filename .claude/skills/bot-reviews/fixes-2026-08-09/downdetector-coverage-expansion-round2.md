---
title: Downdetector Australia coverage expansion, round 2 — small-ISP activation + Australian energy retailers
date: 2026-08-10
author: Chief Engineer (Claude Sonnet 5)
status: DELIVERED — 5 small-ISP sources activated, 3 energy retailers registered + activated, all live-verified through the real production adapter
mission: Captain-directed follow-up to downdetector-adapter-implemented.md
  (19 sources registered, 5 small ISPs left inactive for budget reasons),
  brightdata-provisioning.md, and external-fetch-hard-cap.md (real DB-backed
  hard-cap circuit breaker built earlier tonight, making overspend
  impossible regardless of what's activated).
---

# Mission Summary

Two tasks: (1) re-evaluate whether the 5 small-ISP Downdetector AU sources
(iiNet, Dodo, Aussie Broadband, Superloop, Activ8me) left inactive in
tonight's original build now have real, sustainable budget headroom given
everything that changed later the same night (hard-cap circuit breaker,
tiered cadence, Bright Data provisioning); (2) check whether Australian
energy retailers (Origin, AGL, EnergyAustralia, Alinta) exist on
Downdetector AU at all, and register/activate them if they do and budget
allows.

**Result: all 5 small-ISP sources activated. 3 energy retailers (Origin
Energy, AGL, EnergyAustralia) confirmed real and registered+activated.
Alinta Energy confirmed absent** (checked twice, real "page not found"
response both times, not a timeout/guess). All 8 newly-activated sources
were live-verified end-to-end through the real production
`DowndetectorAdapter.collect()` code path — not a manual curl/scrape
side-test.

# Part 1 — Small-ISP activation

## Fresh headroom check (re-verified 2026-08-10, not trusted from earlier tonight)

Re-derived from the live registry and the real hard-cap circuit breaker
(`intelligence/ingestion/external_fetch_budget.py`, applied earlier tonight
— ceiling 850/1,000 for Firecrawl, 4,500/5,000 for Bright Data), not from
any prior document's numbers:

**Firecrawl-path committed volume before this change**, confirmed against
the live registry (`AEMO Market Notices`, `Fastly Status` both
`source_type=scrape`/`active=true`; 5 telecom Downdetector sources
active — Telstra, Optus, TPG, Vodafone, NBN Co):

- 7 sources × 1×/day × 30 days = 210/month (`_daily_collection_job`, 06:00 AEST)
- + 7 sources × 2 (fortnightly `_brief_job`, `BriefGenerator.generate()`
  independently confirmed to call `collect_all()` the same way) = 14/month
- + Telstra/Optus priority-tiered cadence (`_priority_tiered_collection_job`,
  120-min interval, 07:00-19:00 AEST = 6 ticks/day) = 2 × 6 × 30 = 360/month
- **= 584/month committed, against an 850 ceiling → 266/month (31.3%) headroom**

This matches `cadence-tiering-and-learned-threshold.md`'s same-day figure —
independently re-derived here from the registry + scheduler code, not
copy-pasted.

**Adding the 5 small ISPs** (all `sector="telecom"` per
`downdetector_adapter.sector_for_slug()`, routed to the Firecrawl path, NOT
tiered — small ISPs are deliberately excluded from
`scheduler._PRIORITY_TIERED_SOURCE_NAMES`, matching the Captain's own
original brief):

- 5 × 1×/day × 30 = 150/month
- + 5 × 2 (fortnightly) = 10/month
- **= 160/month addition**

**New Firecrawl total: 744/month against the 850 ceiling → 106/month
(12.5%) of real headroom remaining**, plus 256/month of distance from the
true 1,000/month vendor cap (three layers of margin: ceiling headroom,
ceiling-to-cap margin, and the circuit breaker itself as a hard backstop
that refuses further calls outright rather than overspending if this
projection is ever wrong in practice — built earlier tonight specifically
for this purpose).

**Decision: activate all 5 at the existing once-daily cadence, not tiered.**
106/month is real, positive, sustainable margin — tighter than before
(266→106) but not maxed out, and the platform now has a hard technical
backstop (not just a math projection) if anything unexpected pushes past
it. Deliberately did NOT tier the small ISPs (would have consumed the
remaining headroom for no clearly-justified benefit — small-ISP outages are
lower blast-radius than the Big-2 telcos already tiered).

## What was changed

- `intelligence_source_registry` (live DB): `active=true` for all 5 rows,
  each with a `[REACTIVATED 2026-08-10 (coverage expansion round 2): ...]`
  note appended documenting the real headroom math.
- `tools/intelligence/sources_live.csv`: same 5 rows, `active=True`, same
  note appended (CSV is this repo's tracked source of truth per
  `seed_source_registry.py`'s own header).
- `tools/intelligence/seed_source_registry.py`: same 5 `SOURCES` entries
  flipped to `"active": True`, notes synced to match.

## Registry hygiene found and fixed while working this file (disclosed)

Found real, pre-existing drift while editing this file: the 9
banking/government Downdetector `SOURCES` entries in
`seed_source_registry.py` still showed `"active": False` with the
*pre-Bright-Data* deactivation note, even though the live DB and the CSV
(synced by commit `6648cf13`, "Sync CSV active flag for 9 banking/gov
Downdetector sources") have correctly shown `active=true` with the real
Bright Data activation note since earlier tonight — the Python `SOURCES`
list itself was never updated after that sync (last touched by an earlier
commit, `fb6a8ac8`, before the Bright Data zone was verified).

This is a real, live risk: running `python tools/intelligence/
seed_source_registry.py` (without `--dry-run`) would have silently
**reverted 9 live, working sources back to inactive** — the exact defect
class this exercise exists to prevent. Not something this mission was
asked to fix, but directly relevant to the exact file/rows being edited for
the ISP activation, low-risk (a straight sync from the file's own stated
canonical source, the CSV, with zero ambiguity about the correct value),
and cheap — fixed here rather than disclosed-and-left. All 9 rows' `active`
flag and `notes` text in `SOURCES` now match the CSV exactly.
`seed_source_registry.py --dry-run` after the fix reports 22/22
Downdetector sources correctly active.

## Live verification (real production adapter, not a manual test)

All 5 ISPs run through `DowndetectorAdapter.collect()` directly (real
network call via the real production Firecrawl fetch path, no mocks):

```
Downdetector AU — iiNet             -> collect() OK, items: 0
Downdetector AU — Dodo              -> collect() OK, items: 0
Downdetector AU — Aussie Broadband  -> collect() OK, items: 0
Downdetector AU — Superloop         -> collect() OK, items: 0
Downdetector AU — Activ8me          -> collect() OK, items: 0
```

0 items is the correct, expected result on a real quiet day (same
AWS/Azure "intermittent" convention every other adapter in this codebase
follows) — confirms the fetch, parse, and gate all executed correctly
end-to-end, not that nothing happened. Firecrawl usage counter
(`external_fetch_usage`) confirmed incrementing correctly across these real
calls (4 → 9, i.e. +5, matching exactly 5 real Firecrawl calls).

# Part 2 — Australian energy retailers

## Method

The build session's own `firecrawl` CLI credential was invalid/expired in
this session (`Unauthorized: Invalid token`, confirmed against both the map
and scrape subcommands, and against a known-good URL) — could not repeat
the exact tool used to discover the original 19 slugs. `WebFetch` also
outright refuses `downdetector.com.au` (Cloudflare-protected, same class of
block already documented). Confirmed this session is running directly on
the real production host (`hostname` = `vmi3371936`, matching
`intelligence-scheduler.service`'s own systemd unit and prior missions'
commit author) — a plain `urllib` GET from here still returns the same real
Cloudflare 403 challenge already documented, confirming the block is
Cloudflare-side, not sandbox-egress-specific.

Given that, used the platform's own already-provisioned, already-verified
Bright Data Web Unlocker fetch path (`intelligence.ingestion.
brightdata_fetch.fetch_html()`, the real production module) directly
against a batch of candidate slugs — the same real fetch path these sources
use in production, not a side-channel. First established a reliable
"real company page" vs "real 404" baseline (a deliberately-fake slug
returns a genuine, verifiable Downdetector "page not found" page — distinct
from the correct real pages), then tested candidates for Origin, AGL,
EnergyAustralia, and Alinta, plus a handful of other AU energy-sector names
as a sanity check (Red Energy, Simply Energy, Momentum Energy, Powershop,
Ergon Energy, Ausgrid, Essential Energy — network-timeout-inconclusive on
several of these smaller/non-retailer names, not chased further since they
weren't named in the brief).

## Results

| Candidate | Slug that works | Result |
|---|---|---|
| **Origin Energy** | `originenergy` (no hyphen) | **Real** — company name "Origin Energy" matched, real parsed status/count |
| **AGL** | `aglenergy` (no hyphen) | **Real** — company name "AGL Energy" matched, real parsed status/count |
| **EnergyAustralia** | `energyaustralia` (no hyphen) | **Real** — company name "Energy Australia" matched, real parsed status/count |
| **Alinta Energy** | `alintaenergy` (tried twice) | **Confirmed absent** — genuine Downdetector "page not found" response both times, not a timeout |
| Red Energy, Simply Energy, Momentum Energy, Powershop, Ergon Energy, Ausgrid, Essential Energy | various | Inconclusive (network timeouts against Bright Data on several attempts) — not named in the brief, not chased further |

Slug convention differs from telecom/banking: energy retailers use a
**single word, no hyphen** (`originenergy`, not `origin-energy` or
`origin`) — confirmed by testing both shapes for each candidate before
concluding a miss.

Real quiet-day baseline observed at registration time (single snapshot, all
3, `no_problems` status): **2 reports each** — same low order of magnitude
as government's previously-observed baseline (~1-2), well below banking's
(~3) and far below telecom's (~34 for Telstra).

## Budget headroom check

Energy retailers are routed to the **Bright Data** fetch path (like
banking/government), a deliberate choice — not simply following the sector
pattern mechanically, but because Bright Data has far more real headroom
than Firecrawl does right now (106/month after the ISP activation above,
vs. Bright Data's much larger margin below), and there's no content-shape
reason energy needs Firecrawl specifically. This required adding `"energy"`
as a genuine new sector (not lumping it into `"other"`, which would have
(a) misrouted it to the tighter Firecrawl budget, and (b) produced
incorrect classifier-facing text — see "Code changes" below).

**Bright Data committed volume before this change**, confirmed live (9
banking/government sources active, 4 of them — NAB/ANZ/CBA/Westpac —
priority-tiered):

- 9 × 1×/day × 30 = 270/month + 9 × 2 (fortnightly) = 18/month = 288/month baseline
- + 4 tiered banks × 6 ticks/day × 30 = 720/month
- **= 1,008/month committed, against a 4,500 ceiling**

**Adding 3 energy sources** (once-daily only, not tiered):

- 3 × 30 = 90/month + 3 × 2 (fortnightly) = 6/month = **96/month addition**

**New Bright Data total: 1,104/month against the 4,500 ceiling →
3,396/month (75.5%) of real headroom remaining** — a large, comfortable
margin, not close to maxed out. **Decision: activate all 3 at the existing
once-daily cadence.**

## Code changes (new `energy` sector, not force-fit into an existing bucket)

`intelligence/ingestion/downdetector_adapter.py`:

- New `_ENERGY_SLUGS = {"originenergy", "aglenergy", "energyaustralia"}`,
  wired into `sector_for_slug()`.
- `_fetch_html()`'s sector-based routing extended:
  `if sector in ("banking", "government", "energy")` → Bright Data;
  everything else (telecom/other) → Firecrawl, unchanged.
- New `elif sector == "energy":` branch in `_build_item_text()`.
  **Deliberately avoids energy-grid language** ("electricity", "power
  outage", "gas supply", "grid", "blackout") for two real reasons: (1)
  accuracy — a Downdetector AU retailer page tracks user reports about the
  retailer's own digital services (billing app, online account portal,
  customer service), not the physical electricity/gas network (that's the
  distribution network operator's job — Ausgrid/Energex/etc — an
  unregistered, different source category); (2) push-alert routing
  correctness — `classifier.py`'s `energy_disruption` event type is **not**
  a member of `intelligence_store.py`'s `_OUTAGE_EVENT_TYPES`, so text that
  classified there would silently never reach the push-alert pipeline even
  if this adapter's own two-layer gate passed. Phrasing mirrors the
  existing, proven banking branch's pattern (same "outage"/"unavailable"/
  "service disruption" keywords that already correctly land on
  `technology_outage`).

`intelligence/ingestion/downdetector_thresholds.py`:

- New `"energy": 20` in `_BOOTSTRAP_DEFAULTS`, matching government's
  interim default (closest real observed baseline, ~2 vs government's
  ~1-2) — same proportional-spike reasoning as the existing banking/
  government defaults, disclosed as an interim number pending real
  accumulated history (same 21-distinct-day minimum, same LLM-learned
  pipeline from migration 0121, applies unchanged).

`core/infrastructure/supabase/migrations/0136_downdetector_energy_sector_constraint_expand.sql`
(applied live via Supabase MCP, mirrored here): widened the `sector` CHECK
constraint on both `downdetector_baseline_history` and
`downdetector_learned_thresholds` (migration 0121) from
`('telecom','banking','government','other')` to add `'energy'` — additive,
non-breaking, same safe pattern already used repeatedly tonight for other
CHECK-constraint widenings on this schema. Without this, `_log_observation()`
would have silently failed (best-effort try/except) for every energy fetch,
forever, breaking the threshold-learning pipeline for this sector.

## Registration

3 new rows in `intelligence_source_registry` (live), `tools/intelligence/
sources_live.csv`, and `seed_source_registry.py`'s `SOURCES` list — same
15-field shape as the other 19, `category=critical_infrastructure`,
`source_type=downdetector`, `jurisdiction=AU`, `confidence_weight=0.85`,
`priority_rank=2`, `content_expectation=intermittent`,
`useful_life_days=2`, `active=true`:

- `Downdetector AU — Origin Energy` → `https://downdetector.com.au/status/originenergy/`
- `Downdetector AU — AGL` → `https://downdetector.com.au/status/aglenergy/`
- `Downdetector AU — EnergyAustralia` → `https://downdetector.com.au/status/energyaustralia/`

(Note: the task brief referred to a "domain_registry entry" as part of the
registration pattern. Checked live — `domain_registry` is this platform's
scheduler-job/heartbeat-domain table (`domain_key`,
`expected_cadence_minutes`, `grace_period_minutes`), unrelated to
per-source registration; none of the original 19 Downdetector sources have
a `domain_registry` row either. Interpreted as referring to
`intelligence_source_registry`, the actual per-source DB table, which is
what was registered.)

## Live verification (real production adapter, not a manual test)

All 3 run through `DowndetectorAdapter.collect()` directly (real network
call via the real production Bright Data fetch path, no mocks):

```
Downdetector AU — Origin Energy      -> collect() OK, items: 0
Downdetector AU — AGL                -> collect() OK, items: 0
Downdetector AU — EnergyAustralia    -> collect() OK, items: 0
```

0 items is correct/expected (quiet day, both gate layers correctly did not
fire). Origin Energy and EnergyAustralia needed a longer-than-default
timeout on a couple of attempts (`BRIGHTDATA_TIMEOUT_SECONDS` default is
45s; both succeeded reliably at 90s) — real, observed intermittent latency
on these two pages specifically, not a code defect (confirmed by getting
clean, identical real content back once given more time). Not changing the
platform-wide default (would affect all 12 Bright Data callers for a
latency issue observed on 2 of them) — flagged here in case it recurs in
production and needs a closer look. AGL succeeded on the first attempt at
the default timeout with no issue.

Also independently verified the real, full push-alert eligibility path for
all 3 using the actual production `classify()` and
`intelligence_store._has_outage_language()`/`_is_downdetector_source()`
functions against a synthetic outage-scale text sample: all 3 correctly
land on `event_type=technology_outage`, `customer_impact=high`,
`confidence=0.77` (above the 0.65 push floor), pass `_has_outage_language`,
and correctly match the Downdetector guard-5/6 bypass — confirming a real
energy outage would actually reach a push alert, not just pass this
adapter's own gate silently.

# Verification summary

- `python3 -m py_compile` clean on all touched files.
- `pytest tests/test_downdetector_priority_cadence.py
  tests/test_downdetector_thresholds.py` — 36/36 pass, no changes needed
  (this mission didn't touch cadence/threshold-recompute logic, only sector
  classification and bootstrap defaults).
- `pytest tests/test_intelligence_*.py` (full suite) — 196/199 pass, same 3
  pre-existing failures already documented in
  `cadence-tiering-and-learned-threshold.md` (`test_media_source_low_relevance_suppressed`,
  `test_load_returns_sorted_list`, `test_trends_stable` — live-data-dependent,
  unrelated to any file this mission touched). No new regressions.
- `seed_source_registry.py --dry-run`: 163 total sources (was 160),
  22/22 Downdetector sources correctly `active`.
- Real production registry loader
  (`intelligence.persistence.intelligence_store.load_source_registry()`)
  confirmed loading exactly 22 active Downdetector sources live.
- All 8 newly-activated sources (5 ISPs + 3 energy) live-fetched
  successfully through `DowndetectorAdapter.collect()` — the real
  production code path, real network calls, no mocks.

# Budget snapshot (post-mission, both providers)

| Provider | Committed before | Added this mission | Committed after | Ceiling | Headroom after |
|---|---|---|---|---|---|
| Firecrawl | 584/month | +160/month (5 ISPs) | 744/month | 850 | 106/month (12.5%) |
| Bright Data | 1,008/month | +96/month (3 energy) | 1,104/month | 4,500 | 3,396/month (75.5%) |

Both remain under their ceiling with real, disclosed margin — Firecrawl
tighter than before but not maxed out, Bright Data very comfortable. The
DB-backed hard-cap circuit breaker (`external_fetch_budget.py`) is the real
backstop in both cases regardless of whether this projection holds exactly
in practice.

# Mission Status

Delivered. All 5 small-ISP sources activated (real headroom: 106/month,
12.5%, on Firecrawl). Origin Energy, AGL, and EnergyAustralia confirmed
real, registered, and activated (real headroom: 3,396/month, 75.5%, on
Bright Data). Alinta Energy confirmed absent from Downdetector AU — a real,
disclosed gap, not forced. All 8 newly-activated sources live-verified
through the real production adapter. A pre-existing CSV/SOURCES-list drift
for the 9 banking/government sources was found and fixed while working this
file (not silently left, given the real risk of an unguarded future
`seed_source_registry.py` run reverting live sources).
