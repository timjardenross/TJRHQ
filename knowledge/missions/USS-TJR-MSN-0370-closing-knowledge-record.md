# USS-TJR-MSN-0370 — Follow-up Closeout (Ruff full triage, ADR-030 fix, ADR citations, Supabase #157) — Closing Record

Source: follow-up items explicitly flagged at USS-TJR-MSN-0369's close. All addressed this pass except Vercel-blocked lcars-portal deps, held per user instruction.

## Ruff full triage (4 parallel directory-scoped streams)

- **Before:** ~3,395 manual-judgment findings repo-wide (after MSN-0369 Stream 2's 3,420-finding autofix subset).
- **After:** 0. Confirmed via fresh `ruff check .` on the fully merged tree.
- Split by top-level directory (not by rule) to keep parallel workers' file ownership exclusive: `platform-runtime/` (1295→0), `core/` (977→0), `intelligence/`+`tools/` (617→0), `telegram-bots/`+misc (503→0).
- BLE001 (blind except, 1,462 repo-wide — the dominant bucket) handled per user's explicit policy: narrowed real production callsites to specific exceptions or added proper logging; suppressed test/fixture/mock callsites with dated reasons. No mechanical globbing.
- DTZ family (naive datetime, ~435 repo-wide) fixed as real correctness work, not just lint-satisfaction — each replacement checked for semantic equivalence to the original.
- **Real bugs found and fixed along the way** (not just lint noise):
  - `core/coordination/number_one.py` — undefined `log` (live NameError landmine) in a function documented as "never raises".
  - `platform-runtime/tts_edge.py` — blocking file read inside `async def`, stalling the bot's event loop; moved to `asyncio.to_thread`.
  - `telegram-bots/xo/app.py`'s `/restart_bots` handler — blocking `subprocess.run()`/`Popen()` calls inside the async event loop; moved to `asyncio.to_thread`/`create_subprocess_exec`.
  - `platform-runtime/captain_notifications.py` — truncated `%z` timezone offset causing wrong staleness calculations.
  - `platform-runtime/mission_lifecycle.py` — shadowed-import `UnboundLocalError`, plus a separate latent `NameError` in its Supabase-fallback path.
  - `intelligence/correlation_synthesis.py` — computed `r_value`/`sample_size` silently dropped before reaching Captain-facing brief text.
  - `tools/integrate_lessons.py` — stray `PYEOF` heredoc terminator left in the file.
  - `intelligence/test_msn_0013bcd.py` — a computed value was never asserted despite the comment saying it should be.
- 3 known gaps flagged (not guessed at), documented inline with `KNOWN GAP` comments: an unenforced source-governance filter in `content_intelligence_service.py`; two emergency-alert adapters whose source feeds carry no timezone info at all; `tools/health-osint/`'s hyphenated directory name (a rename would be a real production-risk change, out of scope).
- Merging the 4 branches surfaced 9 additional findings from merge/concurrent-mission drift (a pre-existing `.vulture_whitelist.py` file none of the 4 streams owned, and `platform-runtime/test_wp1_wp2_wp3.py` which landed on main from an unrelated concurrent mission after the streams' scans) — closed out directly during the merge pass, same standard (suppress with dated reason or fix, never silently skip).
- **CI gate flipped to blocking** for ruff-check (was informational since MSN-0369, pending exactly this triage).

## ADR-030 test/implementation mismatch

- Root cause: `platform-runtime/test_build_router_alignment.py` tested a "mission ID routes through Engineering Router with backend/mode selection" design that never actually existed in `commands/mission_brief.py`'s git history (confirmed via `git log --all -S`) — the test was stale, not the implementation.
- Note: a concurrent session/mission independently found and fixed the identical root cause on `main` while this stream was running (citing the same evidence — the 2026-09-08 Slack-integration removal, commit `38e554352`). That version was a superset (removed 4 stale test classes vs. this stream's narrower scope) and was kept during the merge.
- ADR-030's own file got a "Resolution" section documenting the evidence trail; this merged cleanly.

## ADR citations (~23 unresolved numbers)

Verified all number-by-number (000–002, 005–012, 014–019, 021, 023, 025–029):
- **1 real citation, filed:** ADR-006 (Supabase-backed advisory memory layer for Number One/research/mission-registry) — `core/coordination/number_one_memory_adapter.py` plus 3 real test suites explicitly reference "ADR-006 Phase 1/2A/3". Filed as low-confidence (scope confirmed, decision drivers/alternatives not recoverable from citations — same honesty tier as ADR-004).
- **22 confirmed noise**, classified: fixture/test data (`enrichment_poc/`, the ghost `temporal_entities_archived_2026` table, ephemeral `data/self-improvement/runs/*/evidence.json` snapshots), the known-stale `ArchitectureIndex.tsx`/`captainReview.ts` UI mock, template/example boilerplate (ADR-001/002), and generic ID-format illustration text (ADR-009). None invented — the honest answer for the vast majority was "not a real citation."

## Supabase #157 investigation

- Confirmed `SyncClient`'s private `_auth_token` mechanism was genuinely removed in supabase-py 2.5.0 (verified by installing and reading source across versions, not trusting the docstring's claim).
- **Found and implemented a real, clean replacement**: `create_client(url, anon_key, options=ClientOptions(headers={"Authorization": f"Bearer {token}"}))`, available since supabase-py 2.4.3 — verified live on 2.4.3/2.7.4/2.24.0/2.31.0. `telegram-bots/xo/scoped_supabase.py` redesigned to use this public API; the private-attribute monkeypatch is gone.
- PR #157's full 2.31.0 target is still blocked, but the reason is now understood precisely: supabase-py ≥2.9.x requires `httpx>=0.26`, incompatible with `python-telegram-bot==20.7`'s hard `httpx~=0.25.2` pin. Needs a PTB upgrade first (out of this stream's scope).
- Shipped a safe intermediate bump instead: supabase 2.3.4 → 2.7.4 + explicit `gotrue<2.9.0` pin. Verified clean `pip install` resolution and 14/14 tests passing.
- **Bonus bug found and fixed**: the already-merged `gotrue==2.12.4` pin (PR #132) was itself unsatisfiable against the pre-existing `httpx<0.26` pin — the live `tg-xo.service` had silently never been reinstalled and was still running the pre-#132 `gotrue==1.3.1`. **This needs a real service redeploy to take effect** — the fix is in the repo, but `tg-xo.service` on the production host needs `pip install -r requirements.txt` + restart to actually pick it up.
- `telegram-bots/revs` has the identical monkeypatch hack but runs PTB 22.8 with no httpx conflict — flagged as an easier follow-up to go straight to supabase 2.31.0.

## Merge conflicts encountered (all resolved, documented per-commit)

- `.secrets.baseline` conflicted on 3 of the 7 branch merges (generated file, line-number drift) — resolved each time via full `detect-secrets` rescan, verified no coverage loss against either merge side before accepting.
- `platform-runtime/test_build_router_alignment.py` conflicted twice (once against the ADR-030 stream, once against the ruff-platformruntime stream) because a concurrent, unrelated mission independently fixed the same root cause on `main` first. Resolved by keeping `main`'s superset version both times — confirmed the surviving test classes were unaffected and current.
- `platform-runtime/recovery_scheduler.py` — modify/delete conflict (ruff branch fixed lint findings in a file a concurrent mission had deliberately deleted as confirmed dead code, commit `96c8e3f9b`). Took the deletion.

## Follow-up work identified (not this mission's scope)

1. `tg-xo.service` needs a real redeploy (`pip install -r requirements.txt` + restart) to pick up both this mission's supabase/gotrue fix and the earlier PR #132 fix it turned out was never actually deployed.
2. `telegram-bots/revs`'s `scoped_supabase.py` — same monkeypatch hack, easier to fix (no httpx/PTB conflict), not done this pass.
3. PR #157's full 2.31.0 target still needs a `python-telegram-bot` upgrade past 20.7 before it can proceed.
4. lcars-portal Dependabot PRs (#160/#162/#168) — held per explicit instruction, still blocked on Vercel free-tier deploy-rate-limit.
5. 3 `KNOWN GAP`-flagged items from the ruff triage pass (source-governance filter, timezone-blind alert adapters, `health-osint` directory naming) — documented inline, not fixed.

---
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017JVSxZPQpDi12bMNMMJt8y
