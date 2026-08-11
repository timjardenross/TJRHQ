# Chief Engineer Architecture Review — Health OSINT Workbench

**Reviewer:** Chief Engineer, USS TJR (Registry USS-TJR-003, Engineering Division, Advisory authority)
**Date:** 2026-08-09
**Subject:** `/health-osint` — live workbench per `lcars-portal/src/lib/workbenches.ts:27-30`
**Method:** Direct code read of the shipped repo (`/opt/starship-endeavour`), live systemd/journalctl inspection on the host, and a direct read-only Supabase query against production tables (via the service-role key already present in `.env`) to check the design doc's claims against actual row-level data — not the doc, not memory, not git-log commentary.

---

## Mission Summary

Assess whether the Health OSINT Workbench — billed in the canonical live-workbench registry as delivering "source reliability, study confidence, and safety escalation" — actually does that in production, and whether the platform should trust what's shipped.

---

## Assessment

### What's real (verified, not assumed)

- **The workbench is not a mock.** All four tabs (`confidence-matrix`, `intelligence-summary`, `source-network`, `threat-assessment`) are backed by real Supabase queries in `lcars-portal/src/app/api/health-osint/{confidence-matrix,intelligence-summary,source-network,threat-assessment}/route.ts` — no hardcoded signal arrays, no `Math.random()` scores. Confirmed by direct query: **344 rows currently in `health_signals`**, spanning all 6 `health_domain` values (treatment 86, performance 61, vaccine 58, epidemiology 56, mental_health 48, supplement 35). This supersedes the "26 signals" figure in prior session memory (`health-osint-workbench-built-2026-08-08.md`) — that was the one-time hand-authored seed from migration `0094_health_osint_seed_signals.sql`; a real ingestion pipeline has since run and grown the pool past the design doc's own 100-200 target (`HEALTH_OSINT_WORKBENCH.md:357`).
- **Auth is genuinely enforced, not decorative.** All four API routes call `requireSession()` and return 401 on no session (`confidence-matrix/route.ts:69-72` and the equivalent block in each of the other three routes). `requireSession()` (`lcars-portal/src/lib/supabase-server.ts:31-36`) checks a real server-side Supabase session, not a client-trusted header. The page itself sits behind `middleware.ts`, which redirects unauthenticated requests to `/login` before any client code runs, and separately scopes the `x-bot-secret` bypass to `/api/*` only (a fix already made platform-wide per the comment at `middleware.ts:47-53`, referencing the SUOC Wave 1 finding). RLS is enabled with `authenticated`-only SELECT and `service_role`-only writes on all 4 core tables plus `health_signal_validation`, correctly using `auth.role() = 'authenticated'` (not the `'authenticated_user'` mistake the migration's own comment says was caught before, at `0093_health_osint_workbench.sql:167-195`).
- **Ingestion is a real pipeline against real external sources**, not a fixture. `tools/health/collect_health_signals.py` pulls PubMed E-utilities, ClinicalTrials.gov REST v2, and 3 curated RSS feeds; runs on `/etc/systemd/system/health-osint-collection.timer` (daily 02:00 UTC), chained to `validate_health_source_accuracy.py` and `recompute_health_signal_scores.py` in one `oneshot` service. The most recent run (2026-08-09 12:00 AEST / 02:00 UTC) succeeded end to end: `Collection complete: {'pubmed_fetched': 69, 'ctgov_fetched': 75, 'rss_fetched': 45, 'saved': 3, 'duplicates': 186, 'sources_auto_registered': 2, 'errors': 2}` — the 2 errors were a transient PubMed `IncompleteRead` and a ClinicalTrials.gov timeout, both non-fatal and logged, not silently swallowed.
- **Caveat on that pipeline: it is one day old in production.** `journalctl -u health-osint-collection.timer` shows the timer was installed 2026-08-08 13:32 AEST and has fired exactly **once** as a scheduled job since (the 2026-08-09 02:00 UTC run above). Everything else that grew the signal count from 26→344 happened via manual backfill runs during that day's development (git log: `a69d0db`, `f516887`, `3e2140e`, `6f32c00`, all dated 2026-08-08/09). The pipeline is real, but its unattended reliability over time is unproven — one clean automated run is not a track record.

### A concrete architecture defect: the source-trust "self-correction" loop can't actually correct most sources

This is the headline finding, and it directly undercuts the workbench's stated purpose of "source reliability."

`health_source_registry.reliability_score` is a Postgres `GENERATED` column (`0093_health_osint_workbench.sql:36-44`) computed from 5 inputs: `publisher_reputation`, `peer_reviewed`, `avg_methodology_quality`, `replication_success_rate`/`retraction_rate`, and `conflict_of_interest_disclosure`/`funding_transparency`. Migration `0098_health_source_validation.sql` was built explicitly, per its own comment, to fix "the exact same 'SRS scoring inert' shape found and fixed on the technical workbench" — i.e., to make this score actually evolve from real evidence instead of sitting at a static seed-time default forever.

But `validate_health_source_accuracy.py:recompute_source_scores()` (lines 101-125) only ever writes `replication_success_rate` and `retraction_rate`. It never touches `publisher_reputation` or `avg_methodology_quality` — the two terms that dominate the formula for any auto-registered source, because `collect_health_signals.py:_get_or_create_source()` (lines 207-242) sets both to conservative defaults (`publisher_reputation = 0.45` unless the journal name matches one of ~35 hand-curated entries in `KNOWN_JOURNAL_REPUTATION`, `avg_methodology_quality = 0.5` always) and nothing in the codebase ever revises them.

I verified the consequence directly against live data:

```
total sources: 130
auto_registered: 114 (88%)
auto-registered publisher_reputation distribution: {0.45: 101, ...13 matched known journals...}
auto-registered reliability_tier distribution: {TIER_4: 103, TIER_3: 11}
overall tier distribution: {TIER_4: 107, TIER_3: 12, TIER_1: 10, TIER_2: 1}
```

Working the formula with `publisher_reputation=0.45`, `avg_methodology_quality=0.5` held at their permanent defaults, even a source with **perfect** validated accuracy (`replication_success_rate=1.0`, `retraction_rate=0`) tops out at `0.45 × 1.2 × 0.5 × 1.5 × 0.75 ≈ 0.30` — below the `TIER_3` floor of 0.45, let alone `TIER_2`'s 0.65. **103 of 130 sources (79%) are structurally locked into TIER_4 for as long as the platform runs**, regardless of how their signals validate over time. And `confidence_level()` (`recompute_health_signal_scores.py:44-57`, mirrored in `collect_health_signals.py:473-486`) maps `TIER_3`/`TIER_4` unconditionally to `LOW` — so a rigorous, adequately-powered RCT auto-registered under an unreviewed journal name will show as LOW confidence forever, no matter how it validates, while the study-quality signal the SRS formula was supposed to weigh is structurally muted. The live confidence distribution bears this out: `LOW: 181, MEDIUM: 149, HIGH: 14` out of 344 — a distribution driven far more by which 12% of sources happen to be hand-curated than by per-study methodology.

This is not a hypothetical design gap — it's a shipped validation loop that looks like it closes the "inert scoring" problem (its own migration comment says so) but, checked against what it actually writes, closes less than half of it.

### A second, smaller design/implementation divergence from the same root cause

The Python `confidence_level()` function collapses `TIER_3`/`TIER_4` into `LOW` unconditionally, but the original seed migration's SQL version (`0094_health_osint_seed_signals.sql:69-76`) and the design doc's confidence mapping (`HEALTH_OSINT_WORKBENCH.md:156-160`) both intend an `UNKNOWN` bucket for genuinely low-quality/low-tier signals. Confirmed live: **0 of 344 signals carry `confidence_level = UNKNOWN`** — the bucket that's supposed to represent "insufficient methodology data" is dead in the running pipeline. Separately, even if it weren't, `intelligence-summary/route.ts` (lines 57-60) only ever buckets `high`/`medium`/`low` — there is no code path that would surface an `UNKNOWN`-confidence signal in that tab at all. Low severity today (nothing is landing there), but it means two independent parts of the system silently diverged from the documented design, and neither would be caught by anything short of reading the code, because there's no test asserting the mapping.

### Source-Trust Network tab is decorative for its main feature

`source-network/route.ts` reads from `health_signal_corroboration` and is honest in its own comment (lines 3-8) that trending has "no historical series stored yet" and reports a flat current-snapshot rather than fabricating direction. That disclosure is good practice. But the same honesty doesn't extend to corroboration itself: **`health_signal_corroboration` has exactly 2 rows**, both inserted by the one-time seed migration (`0094_health_osint_seed_signals.sql:97-113`) on 2026-08-08. No script in `tools/health/` or `core/health/` writes to that table. So as the signal pool has grown to 344, "Cross-Source Corroboration" in the live UI is showing essentially the same 2 hand-placed links from launch day for every source, dressed up as a live corroboration graph. The route's comment frames this favorably ("health signals carry an explicit corroboration table" — unlike the technical workbench's title-overlap heuristic) without disclosing that nothing populates it going forward.

### Zero test coverage, unlike its named sibling

No test exists anywhere in the repo for the 4 health-osint API routes, the workbench page, or the 3 pipeline scripts in `tools/health/`. Checked directly: `grep` across `*.test.ts(x)` and `*.py` test files repo-wide for `health-osint`, `health_signals`, `health_source_registry` returns nothing outside `tools/health/` itself. This matters because commit `83386e9` explicitly claims to "bring health-osint to parity with intelligence-workbench" — but the sibling Technical Intelligence Workbench has at least one real route-logic test (`api/intelligence-workbench/__tests__/operational-signals.test.ts`); Health OSINT has none. Given the categorization/escalation logic in these routes is real business logic (`categorize()` in confidence-matrix, the probability/impact/confidence escalation matrix in threat-assessment) and not passthrough, this is a real gap, not a nitpick — the TIER-lock-in bug above is exactly the kind of thing a unit test on `confidence_level()` against `HEALTH_OSINT_WORKBENCH.md`'s own documented mapping would have caught before it shipped.

### Infrastructure drift: the daily ingestion job is not version-controlled

`health-osint-collection.service` / `.timer` — the job that runs collection + validation + recompute daily and is the sole source of everything this workbench displays — exist only at `/etc/systemd/system/` on the live host. There is **no copy anywhere in the repo**. Contrast with its sibling job: `health-intelligence-weekly.service`/`.timer` (a separate, unrelated job — see note below) **is** checked in at `deploy/health-intelligence-weekly.service` / `deploy/health-intelligence-weekly.timer`, and I confirmed byte-for-byte the live unit matches the repo copy. So the platform has an established convention for versioning these units, and this workbench's most important operational component doesn't follow it. If the VM is rebuilt, the exact schedule, environment file path, and 3-step `ExecStart` chain for this workbench's entire data pipeline exists nowhere except `systemctl cat` on a machine that may not exist anymore.

### A naming trap worth flagging even though it isn't a functional bug today

`health-intelligence-weekly.timer` (description: "USS TJR Weekly Health Intelligence — RSS import + synthesis + article enrichment") sounds like it could be part of the Health OSINT Workbench's pipeline. It is not. I traced `run_weekly_intelligence.sh` → `core/health/weekly_synthesis.py` / `core/health/source_article_enricher.py` and confirmed those write to `intelligence_events`, `intelligence_source_registry`, and `health_insights` — the Technical OSINT and Wellness/human-systems domains respectively (`core/health/source_article_enricher.py:67,77,109,130`). Zero overlap with `health_signals`/`health_source_registry`. This matches the split-ownership pattern prior review already flagged (`suoc-domain-review-health-osint-workbench.md`, per memory, unverified here beyond the code trace above) — two same-named-domain systemd jobs doing unrelated things is a real "which job actually feeds this workbench" trap for whoever's on call next.

### Design-doc safeguard not implemented (low practical risk, but disclosed as a gap)

`HEALTH_OSINT_WORKBENCH.md:383` calls for redacting patient identifiers from adverse-event reports before storage. No redaction step exists anywhere in `collect_health_signals.py`. In practice this is low-risk today because the only ingestion sources are PubMed/ClinicalTrials.gov/RSS — public aggregate research data, not raw patient records — so PHI exposure is unlikely by construction of the source, not by a safeguard actually written in code. Worth noting as a gap that would matter the moment any less-curated source (e.g., a forum/social listening feed) gets added.

---

## Recommendations

Ordered by what actually threatens the workbench's stated purpose vs. what's cleanup:

1. **Fix the validation loop to close the SRS-inertness gap it was built to close.** Either (a) have `validate_health_source_accuracy.py:recompute_source_scores()` also revise `avg_methodology_quality` from the actual validated signals' `methodology_quality_score` for that source, and let `publisher_reputation` be earnable through a documented graduation rule (e.g., N validated-accurate signals with no inaccurate ones over M days → step reputation up within a capped range), or (b) if `publisher_reputation` is meant to stay permanently hand-curated by design, document that explicitly and stop implying (via the migration comment) that the validation loop makes reliability_score "real, evolving values" for auto-registered sources — right now the comment overstates what the code does. This is a Major architecture-behavior question (changes what "trust" means for 79% of sources), so it needs a decision, not a silent fix — flagging for Captain/Chief of Staff sign-off on which path.
2. **Version-control the `health-osint-collection` systemd units.** Add `deploy/health-osint-collection.service` and `.timer` mirroring the pattern already established for `health-intelligence-weekly`. Mechanical, low-risk, should just happen.
3. **Either build a real corroboration-detection step or relabel the tab's claim.** Right now "Cross-Source Corroboration" implies an ongoing analysis; it's actually a frozen 2-row seed. Smallest honest fix: extend the route's existing disclosure comment into the UI itself (the `note` field pattern it already uses for trending) so the Captain isn't reading a graph that looks live but isn't.
4. **Add route-level tests for the 4 API handlers**, at minimum covering `categorize()`, `confidence_level()`, and the threat-assessment escalation matrix against the exact mapping in `HEALTH_OSINT_WORKBENCH.md` — this is what would have caught the TIER_3/4 → UNKNOWN vs LOW divergence before it shipped quietly.
5. **Let the pipeline run unattended for 1-2 more weeks before treating its reliability as proven.** One clean scheduled run isn't a track record; this is a "watch, don't act on yet" item, not a blocker.

---

## Next Actions

- Immediate/mechanical, no sign-off needed: item 2 (check the systemd units into `deploy/`).
- Needs Captain/Chief of Staff decision before any code changes: item 1 (validation-loop fix — it's a platform-wide trust-scoring behavior change, escalating per the persona's own rule against carving out "small, contained" exceptions).
- Recommend as next sprint-sized piece of work, not urgent: items 3 and 4.

---

## Mission Status

Advisory only. No code changes made. Item 1 (validation-loop fix) requires Captain sign-off before implementation — it changes how source trust is computed platform-wide for this workbench, not a contained fix. Items 2-4 are lower-risk and could proceed on ordinary engineering judgment once prioritized.
