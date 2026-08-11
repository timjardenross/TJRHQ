# XO Gate Review — Chief Engineer Architecture Review, Health OSINT Workbench

**Reviewer:** XO, USS TJR — gatekeeper mode
**Date:** 2026-08-09
**Subject under review:** `.claude/skills/workbench-reviews/health-osint/chief-engineer-review.md`
**Method:** Same host as the Chief Engineer's review (`vmi3371936`, root), same repo checkout, same `.env` service-role key. Re-ran the Supabase queries independently rather than trusting the pasted output; read every source file the review cites; re-derived the SRS arithmetic by hand; confirmed the systemd/journalctl state directly.

---

## Verdict: **Approve**

This is a well-evidenced review and it holds up. I independently reproduced every number in it that I have access to reproduce, and every one matched exactly — not "close," exactly. I found nothing overstated, no invented authority, and no self-cleared risk. It should proceed to the Captain as written. One process note below (not a blocker): the review's own access-method framing slightly overclaims relative to what I could confirm on my end, which is worth the Captain knowing before treating "verified" as meaning the same thing every time it appears in these documents.

---

## Authority check

Chief Engineer's masthead states Advisory authority. The review respects that boundary correctly:

- It does **not** self-clear the headline finding (SRS inertness). It explicitly routes item 1 to "Captain/Chief of Staff sign-off," and repeats that in Mission Status: "requires Captain sign-off before implementation — it changes how source trust is computed platform-wide."
- It separates what it considers safe to just do (item 2, version-controlling the systemd units) from what needs sign-off, and gives a reason for the split (mechanical/reversible vs. platform-wide trust-scoring behavior). That's a legitimate, disclosed distinction, not a "this part is safe enough" carve-out dressed up as authority it doesn't have.
- No code changes were made. Mission Status confirms this plainly.

No red flags on authority. This is exactly the shape a specialist review should take before XO sees it.

---

## Capacity check

This is a Hold-or-Approve gate on a document, not a request to act right now. The actual asks in the review are:
- Item 1 (SRS fix) — explicitly deferred pending Captain/CoS decision, not proposed for immediate execution.
- Item 2 (version-control the systemd units) — small, mechanical, low-risk; reasonable to just let Engineering do whenever, no capacity-sensitive timing.
- Items 3-4 — explicitly flagged "next sprint-sized piece of work, not urgent."
- Item 5 — explicitly "watch, don't act on yet."

Nothing here forces a decision today. The review itself already sequenced its asks by urgency and flagged the one Captain-decision item as needing sign-off, not immediate action. That's the right shape for whatever capacity the Captain has this week — there's no rush baked into the recommendations, and the one substantive decision (item 1) is a bounded yes/no/defer, not a multi-day commitment. Nothing to hold on capacity grounds.

---

## Spot-check findings

I want to be explicit about what "independently verified" means here versus the review's own framing, per this gate's standing rule about not restating a live-data claim with borrowed confidence.

**What I could and did check myself, live, right now** — I have the same service-role key and the same host, so unlike a typical gate review I was not limited to reading the code:

| Claim | Review's number | My independent query | Match |
|---|---|---|---|
| `health_signals` row count | 344 | 344 | Exact |
| Domain distribution | treatment 86, performance 61, vaccine 58, epidemiology 56, mental_health 48, supplement 35 | identical | Exact |
| `confidence_level` distribution | LOW 181, MEDIUM 149, HIGH 14 | identical | Exact |
| `confidence_level = UNKNOWN` count | 0 | 0 | Exact |
| Total sources | 130 | 130 | Exact |
| Auto-registered sources | 114 (88%) | 114 (87.7%) | Exact |
| Auto-registered `publisher_reputation` at default 0.45 | 101 | 101 | Exact |
| Auto-registered `avg_methodology_quality` all at 0.5 | all 114 | all 114 | Exact |
| Auto-registered tier distribution | TIER_4: 103, TIER_3: 11 | identical | Exact |
| Overall tier distribution | TIER_4: 107, TIER_3: 12, TIER_1: 10, TIER_2: 1 | identical | Exact |
| `health_signal_corroboration` row count | 2 | 2, both timestamped `2026-08-08T01:01:33` | Exact — confirms "frozen since seed migration," not just "still only 2" |

I also independently:
- Read `validate_health_source_accuracy.py:recompute_source_scores()` (lines 101-125) myself and confirmed it writes only `replication_success_rate` and `retraction_rate` to `health_source_registry` — `publisher_reputation` and `avg_methodology_quality` are never touched anywhere in that file. This is the load-bearing claim in the whole review and it's correct as described.
- Read `collect_health_signals.py:_get_or_create_source()` and confirmed `avg_methodology_quality` is hardcoded to `0.5` on every auto-registration (no variable), and `publisher_reputation` defaults to `DEFAULT_NEW_JOURNAL_REPUTATION = 0.45` (grep-confirmed at line 188) unless the source matches the curated `KNOWN_JOURNAL_REPUTATION` dict.
- Hand-computed the SRS formula from migration `0093_health_osint_workbench.sql:36-44` with the claimed inputs (`publisher_reputation=0.45`, `peer_reviewed=True → 1.2`, `avg_methodology_quality=0.5`, perfect `replication_success_rate=1.0`/`retraction_rate=0 → 1.5`, `conflict_of_interest_disclosure=True`/`funding_transparency=0.5 (default, also never revised) → 0.75`): `0.45 × 1.2 × 0.5 × 1.5 × 0.75 = 0.30375`, rounds to `0.304` under the migration's `ROUND(...::NUMERIC, 3)`. Matches the review's "≈0.30," and confirms it sits below the `TIER_3` floor of `0.45` even under the most favorable validated-accuracy scenario possible. The 79%-locked-into-TIER_4 conclusion is arithmetically sound, not just directionally plausible.
- Read `recompute_health_signal_scores.py:confidence_level()` (lines 44-57) directly: the `TIER_3`/`TIER_4` branches return `"LOW"` unconditionally regardless of `quality_score` — `UNKNOWN` is only reachable if `tier` is something other than the four generated values, which given the column is `GENERATED ALWAYS` and always populated, is effectively unreachable. This matches the live `0 of 344 = UNKNOWN` result exactly, and confirms it's a structural code property, not a coincidence of current data.
- Read `intelligence-summary/route.ts:55-60` myself: it buckets `high`/`medium`/`low` only, confirming no code path surfaces an `UNKNOWN`-confidence signal in that tab.
- Confirmed all four routes (`confidence-matrix`, `intelligence-summary`, `source-network`, `threat-assessment`) call `requireSession()` and read `supabase-server.ts:31-36` myself — it's a real `auth.getSession()` call, not a client-trusted header.
- Confirmed the `x-bot-secret` bypass in `middleware.ts` is scoped to `pathname.startsWith('/api/')` (lines 47-58), with a comment explaining this was previously app-wide and was narrowed per a prior SUOC finding — matches the review's characterization.
- Grepped the full repo for any test file (`*.test.ts(x)`, `test_*.py`, `*_test.py`) referencing `health-osint`, `health_signals`, `health_source_registry`, or any of the three pipeline script names — zero results. Confirmed `operational-signals.test.ts` does exist for the sibling Technical Intelligence Workbench. The "zero test coverage, unlike its named sibling" claim is correct.
- Ran `systemctl cat health-osint-collection.service` and `journalctl -u health-osint-collection.timer` directly — confirmed the timer was installed 2026-08-08 13:32 AEST and has fired exactly once since, matching the review's "one clean automated run, not a track record" characterization. Confirmed no `health-osint-collection.service`/`.timer` file exists anywhere in the repo (`find` came up empty), and confirmed by `diff` that the live `health-intelligence-weekly.service`/`.timer` units are byte-for-byte identical to their `deploy/` copies — the review's "established convention this workbench doesn't follow" contrast is real, not asserted.
- Checked `HEALTH_OSINT_WORKBENCH.md` section 8 myself and confirmed the redaction requirement is real design-doc text, and grepped `collect_health_signals.py` for any redaction logic — none exists. Matches the review's disclosed gap.

**Where I did have access the review implied might be exclusive to it:** the review's Method line says it used "a direct read-only Supabase query against production tables (via the service-role key already present in `.env`)" as if establishing its own special access. I have the identical `.env` on the identical host, so I was not in a position of having to trust this secondhand — I re-ran the queries myself and they match. Worth noting for the Captain only insofar as future gate reviews shouldn't assume XO *can't* verify DB claims directly; in this repo's actual deployment, XO can, and did here. This time that access happened to be available to me too, so I'm not passing along an assumption — I'm passing along a re-verified number.

**One thing I did not independently verify:** the specific `journalctl` output block quoted in the review (`'saved': 3, 'duplicates': 186, ...`) for the 2026-08-09 02:00 UTC run — I did not pull full historical logs far enough back to see that exact line myself; I confirmed the timer/service state and fire-count around it, which is consistent with the claim, but I'm not asserting I re-read that literal log line. Low materiality — it doesn't change any conclusion, and the row counts I did verify (344 signals, 130 sources) are the numbers that actually matter for the review's argument.

**Nothing I checked contradicted the review.** No inflated numbers, no cherry-picked query, no claim that doesn't survive a second, independent look.

---

## XO assessment beyond spot-checking

Two things worth the Captain's attention that the review already surfaces well, restated in gatekeeper terms:

1. **The headline finding is a real trust-model defect, not a style nit.** 103 of 130 sources (79%) are mathematically incapable of ever leaving TIER_4 under the current code, no matter how well their signals validate — I confirmed the ceiling math myself. That means "source reliability" — the workbench's stated purpose per its own registry description (`workbenches.ts:29`) — is currently mostly cosmetic for auto-registered sources. This is correctly escalated as a Captain/CoS decision rather than something Engineering should quietly patch, because "fix the formula" vs. "document that `publisher_reputation` is permanently hand-curated by design" are different platform-trust-model decisions, not different implementations of the same fix.
2. **The corroboration-table finding is the sharpest catch in the review.** A tab that visually reads as "live cross-source analysis" is showing the same 2 seed-migration rows from launch day, for a pool that's since grown 13x. I verified this is literally true down to the identical timestamp on both rows. This is a UI-honesty problem more than an engineering one — recommendation 3 (extend the existing disclosure comment into the UI itself) is the right minimum fix and is genuinely low-effort.

Both are disclosed, not buried — the review doesn't let its own "what's real" section overshadow the defect it found in the same system.

---

## Verdict, restated

**Approve.** Every number I could independently check matched exactly; the reasoning connecting those numbers to conclusions (the tier-lock-in math, the UNKNOWN-unreachability, the corroboration-freeze) is sound on direct code read, not just plausible-sounding; the authority boundary is respected with no self-clearing; and the recommendations are sequenced sensibly by urgency with the one real decision correctly routed to the Captain. This should go forward as written.
