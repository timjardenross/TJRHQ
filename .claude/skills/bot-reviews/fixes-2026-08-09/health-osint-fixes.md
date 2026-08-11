# Fix: Source-reliability formula structurally broken — Health OSINT Workbench

**Date:** 2026-08-09
**Fixed by:** Chief Engineer persona (fix task, Captain-authorized per task brief)
**Source finding:** `.claude/skills/workbench-reviews/health-osint/chief-engineer-review.md` (Recommendation 1), approved by `xo-gate-review.md` in the same directory
**File changed:** `tools/health/validate_health_source_accuracy.py`
**Commit:** see git log — `tools/health/validate_health_source_accuracy.py` only

---

## What was found

`health_source_registry.reliability_score` (Health_SRS) is a Postgres `GENERATED` column with 5 multiplicative terms (`0093_health_osint_workbench.sql:36-44`):

1. `publisher_reputation`
2. `peer_reviewed` (boolean multiplier, 1.2/0.8)
3. `avg_methodology_quality`
4. `(replication_success_rate × 0.5) + (1 − retraction_rate × 0.3)`
5. `(conflict_of_interest_disclosure × 0.5) + (funding_transparency × 0.5)`

`validate_health_source_accuracy.py:recompute_source_scores()` — the daily job whose entire purpose (per migration `0098_health_source_validation.sql`'s own comment) is to make this score "real, evolving values… instead of leaving them at static seed-time defaults forever" — only ever wrote term 4 (`replication_success_rate`/`retraction_rate`). Terms 1, 2, 3, and 5 were set once at auto-registration (`collect_health_signals.py:_get_or_create_source()`, `publisher_reputation=0.45`, `avg_methodology_quality=0.5`, `peer_reviewed=True`, `conflict_of_interest_disclosure=True`, `funding_transparency=0.5`) and never revised by any code path.

Verified live before the fix: 114/130 sources (88%) are `auto_registered=true`; 103 of those were `TIER_4`, mathematically capped around SRS≈0.30-0.45 regardless of how well their signals validated, because `avg_methodology_quality` never moved off its 0.5 default. Confirmed the exact arithmetic: `0.45 × 1.2 × 0.5 × 1.241 × 0.75 ≈ 0.251` for a typical auto-registered source with default replication/retraction values.

## What data was actually available (investigation, not assumption)

Read `collect_health_signals.py:_methodology_quality()` and confirmed every ingested `health_signals` row already carries a real, structurally-computed `methodology_quality_score` (0-1, from `study_design`/`sample_size`/`p_value` presence) — computed at collection time, stored, but never aggregated up into the source registry's `avg_methodology_quality`. This is real, already-computed, non-fabricated data — a genuine fix path (a), not a case needing invented data.

No equivalent real data source exists for `publisher_reputation` (no citation-index feed) or `funding_transparency`/`conflict_of_interest_disclosure` (no funding-disclosure extraction in the pipeline). Fabricating a "graduation rule" for these was considered (the review's own recommendation floated one) but rejected here: the *rate*, *cap*, and *trigger threshold* of such a rule are policy choices with multiple reasonable answers, not a data-availability fact — genuinely the kind of decision that needs Captain/Chief of Staff sign-off, not a guess. **Not implemented, disclosed below as open.**

## What was implemented

`recompute_source_scores()` now also aggregates `avg_methodology_quality` from `health_signals.methodology_quality_score` (all non-suppressed signals for that source, `min_signals=3` as a light smoothing floor — disclosed choice, lower than the existing `n≥10` accuracy-validation gate because this is a deterministic structural computation, not a noisy heuristic accuracy guess) and writes it to `health_source_registry`.

**Scoping correction made during testing (important):** the first implementation applied this to *all* sources, including the 16 hand-curated seed sources. Tested against live data before shipping and found this was actively wrong, not just untested: The Lancet's RSS table-of-contents feed is dominated by `[Comment]`/`[Perspectives]`/`[Correspondence]`/`[Obituary]`/`[World Report]` items (11 of 15 recent items), which the much weaker RSS title-keyword heuristic (`_infer_study_design_from_title`, vs. PubMed's structured `PublicationType` tag) scores at 0.1-0.55 — dropping The Lancet's `avg_methodology_quality` from a curated 0.90 to a noise-driven 0.289 and its tier from `TIER_1` to `TIER_4`. Reproduced this live, then corrected the code to scope the aggregation to `auto_registered=true` sources only — the exact population the review flagged, and the only population whose `methodology_quality_score` inputs come exclusively from PubMed's structured tags (RSS items only ever look up existing hand-curated sources by name; they never auto-register a new one). Re-verified the corrected code leaves all 16 hand-curated sources untouched.

## Verification against real data (before / after, live Supabase)

Ran the corrected job live (not dry-run) against production. Tier distribution:

| | TIER_1 | TIER_2 | TIER_3 | TIER_4 |
|---|---|---|---|---|
| Hand-curated (16), before | 10 | 1 | 1 | 4 |
| Hand-curated (16), after | 10 | 1 | 1 | 4 (unchanged — correctly untouched) |
| Auto-registered (114), before | 0 | 0 | 11 | 103 |
| Auto-registered (114), after | 0 | 1 | 10 | 103 |

Sample sources, before → after:

| Source | Tier before → after | Score before → after | avg_methodology_quality before → after |
|---|---|---|---|---|
| "The New England journal of medicine" (auto-registered PubMed duplicate of the seeded NEJM row) | TIER_3 → **TIER_2** | 0.542 → 0.848 | 0.5 → 0.783 |
| Journal of affective disorders | TIER_4 → TIER_4 | 0.251 → 0.444 | 0.5 → 0.883 |
| Nutrients | TIER_4 → TIER_4 | 0.251 → 0.385 | 0.5 → 0.767 |
| Vaccine | TIER_4 → TIER_4 | 0.251 → 0.339 | 0.5 → 0.675 |
| British Journal of Sports Medicine | TIER_3 → TIER_3 | 0.475 → 0.522 | 0.5 → 0.55 |
| The Lancet (hand-curated) | TIER_1 → **TIER_1 (unchanged)** | 1.354 → 1.354 | 0.90 → 0.90 (protected) |
| NEJM, Cochrane, WHO, ClinicalTrials.gov (hand-curated) | unchanged | unchanged | unchanged (protected) |

Movement is real and sensible: sources whose actual collected signals are meta-analyses/large RCTs (real PubMed `PublicationType` tags) gained real, evidence-backed score increases, one crossing a full tier. Sources still near the `publisher_reputation=0.45` floor moved up but mostly didn't cross a tier boundary yet — expected and correctly disclosed below, since `publisher_reputation` remains untouched. Also ran `recompute_health_signal_scores.py` (the third pipeline stage) live afterward so `health_signals.confidence_level`/`rank_score` reflect the corrected tiers — 3 signals recomputed, 2 confidence-level changes, 0 errors, matching the one tier crossing above.

Only 5 of 114 auto-registered sources currently have ≥3 signals (the pipeline is ~1 day old per the review's own caveat), so most of the 103 `TIER_4` sources didn't move yet — the mechanism is now correct and will activate as the daily pipeline accumulates more signals per source, not fabricated to move faster than real evidence justifies.

## What was NOT fixed (disclosed, not guessed)

- **`publisher_reputation`** stays permanently at its auto-registration default (0.45, or a curated value for ~35 known journals) for the life of a source. No real per-source reputation-evidence stream exists in this pipeline. A "graduation rule" (N validated-accurate signals over M days → step reputation up within a capped range, per the review's own suggestion) is a real option, but the rate/cap/trigger are policy choices — flagged for Captain/Chief of Staff decision, not implemented here.
- **`funding_transparency` / `conflict_of_interest_disclosure`** — same situation: no funding-disclosure extraction exists anywhere in `collect_health_signals.py`. Left at their creation-time defaults (0.5 / True). No real data source to surface; not fabricated.
- Because of the above, most `TIER_4` auto-registered sources remain structurally hard to lift out of `TIER_4` on `avg_methodology_quality` alone — the max attainable SRS with `publisher_reputation` stuck at 0.45 and perfect replication/methodology is ≈0.61, comfortably above the `TIER_3` floor (0.45) but still below `TIER_2` (0.65). This is a real, disclosed remaining limitation, not something this fix silently papers over.

## Recommendation for the open item

Route `publisher_reputation` graduation policy to Captain/Chief of Staff as the review already recommended — this fix doesn't change that recommendation, it just closes the one piece (`avg_methodology_quality`) that had a real, non-fabricated data source sitting unused in the codebase.
