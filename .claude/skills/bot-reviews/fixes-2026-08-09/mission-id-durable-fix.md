# Mission ID minting — durable self-healing collision check

**Commissioned by:** Captain, following the live drift incident earlier
tonight (`6b13632b` — `.id-counters.json` was never committed to git, was
missing entirely from this checkout, and a fresh `next_id('MSN')` call
returned a stale, colliding `MSN-0144` while real missions were already
past `MSN-0360`). That commit was an explicit stopgap; the durable
self-healing fix — scoped and deferred multiple times across mission
history — is this.

**Delivered:** 2026-08-10, on `main`.

---

## 1. Self-healing collision check in `id_registry.py`

`next_id()` now scans for the *true* highest in-use number for a prefix
before allocating, and auto-bumps the stored counter if it's behind,
rather than trusting `.id-counters.json` blindly.

- `scan_repo_max(prefix)` — shells out to `grep -rhoE` for `{PREFIX}-NNNN`
  (bare or canonical form; the canonical form contains the bare form as a
  substring, e.g. `USS-TJR-MSN-0361` matches on `MSN-0361`) across
  `.md/.py/.ts/.tsx/.json`, the same scope tonight's manual reconciliation
  used. Excludes `node_modules/.git/.next/.venv/__pycache__/dist/build`,
  test directories (`tests/`, `__tests__/`) and test-named files
  (`test_*.py`, `*_test.py`, `*.test.ts(x)`, `*.spec.ts(x)`), plus the
  ID-minting infrastructure's own docs/CLI/tests (`id_registry.py`,
  `tools/mint_id.py`, `tools/mint_server.py`, `tools/test_mint.py`,
  `tools/MISSION-MINTING.md`) since those carry illustrative example IDs
  that aren't real allocations. Runs in ~100ms across the whole repo.
- `scan_table_max(prefix)` — best-effort PostgREST query (via `urllib`,
  no new dependency) against a live table registered per-prefix. Checked
  what's real: **only `missions.mission_id` backs MSN.** `decisions` is
  keyed by `mission_id`, not a `DEC` id; `build_request_inbox.request_id`
  uses an unrelated `AI-<ACTION>-<timestamp>-<rand>` scheme, not `BREQ-NNNN`
  — neither is a real BREQ/DEC store, so neither is registered. Only MSN
  gets a live-table check today; BREQ/DEC fall back to repo-scan-only.
- `true_max_for_prefix(prefix)` combines both signals with provenance.
- `next_id()`: the scan runs *outside* the file lock (read-only, no need to
  serialise it); if the stored counter is behind the scanned true max, it's
  bumped in-place under the lock, immediately before incrementing, and a
  `logging.warning(...)` fires with stored/true_max/source/detail — so
  drift-correction stays visible in logs, not silently masked. If the
  stored counter is already correct (or ahead), the scan is a pure no-op.
- Fails safe throughout: `grep` unavailable/failing, Supabase env vars
  unset, network failure, malformed response — every path returns "no
  signal found" rather than raising, so `next_id()` still always returns
  an ID (matches the function's existing top-level fallback contract).

**A real bug the digit-width choice caught:** the ID format is always
zero-padded 4 digits (5 if the counter ever exceeds 9999). An initial
`{3,5}` digit-count in the scan regex greedily matched *inside* legacy
timestamp-format IDs like `MSN-20260613-102725` (read as `20260`) and
3-digit mock/example strings like `DEC-015` from an unrelated proof-of-
concept module's demo data. Tightened to `{4,5}` — this eliminates both
classes of false positive by construction, since neither a legacy
timestamp ID nor a 3-digit mock string is a valid 4-digit canonical ID.
Caught by testing `scan_table_max('MSN')` against the real `missions` table
(which has one legacy timestamp-format row) before trusting the mechanism.

## 2. `/mission_create` — verified, not duplicated

Read `cmd_mission_create` in `telegram-bots/xo/app.py` fully. It POSTs to
the LCARS Portal's `/api/missions`, which calls `nextId('MSN')` from
`lcars-portal/src/lib/id-registry.ts`, which shells out to
`tools/mint_id.py MSN`, which calls `id_registry.next_id("MSN")` — the
same single-writer path as every other client (documented in
`tools/MISSION-MINTING.md`, MSN-0147). Already the fast path: registered
in `/help`, shows usage on empty args rather than erroring, single HTTP
call with a 10s timeout. No redundant "quick reserve" command built —
there's no real friction here to solve, and building a second minting
entry point would itself be a duplication risk for the exact single-writer
guarantee this whole fix protects.

## 3. `tools/id_counter_drift_check.py`

Read-only companion to the self-healing check, for mission close-out.
Same integration pattern as `tools/registry_staleness_check.py` — checked
how that script gets invoked first (grepped for CI workflows, git hooks,
and every "close-out"/"checklist" doc in the repo) and found **no wiring
exists for it anywhere**: no CI step, no git hook, no checklist doc
references it by name, not even in the `SUOC-Platform-Registry.md` doc its
own docstring cites (that file isn't tracked in this git repo at all —
only in two local backup directories outside version control, never
committed; a separate, pre-existing gap, flagged here for visibility, not
fixed as part of this task). Given that, `id_counter_drift_check.py`
follows the same "manual, run by a human or a future mission, documented
in its own docstring" pattern rather than inventing new CI/hook wiring
inconsistent with everything else in the repo.

It imports `id_registry`'s own scan functions directly (no re-implemented
logic, so the read-only check and the self-healing check can never drift
apart from each other), reports a per-prefix Stored/True-Max/Status table,
and exits 1 if any prefix's stored counter is behind its true max.

## Verification

- `python3 -m py_compile` clean on `id_registry.py`, `tools/mint_id.py`,
  `tools/mint_server.py`, `tools/id_counter_drift_check.py`.
- Collision-check tested directly against isolated counter files (via the
  existing `_MINT_TEST_COUNTER` test-isolation hook, never touching the
  real counter):
  - Stale counter (`{"MSN": 5}`) → correctly detected drift, logged
    `id_registry: counter drift detected for MSN -- stored=5 true_max=361
    (source=repo scan, MSN-0361). Auto-bumping counter before minting.`,
    minted `USS-TJR-MSN-0362`.
  - Correct counter (`{"MSN": 361}`) → no log emitted, no-op, minted
    `USS-TJR-MSN-0362` normally.
  - Counter ahead of true max (`{"MSN": 400}`) → left untouched, minted
    `USS-TJR-MSN-0401` normally (never *lowers* a counter).
- Ran `next_id('MSN')` for real against the live `.id-counters.json`
  (stored at 361 going in, matching the real state after tonight's
  reconciliation): no drift detected (already correct), returned
  `USS-TJR-MSN-0362` — the real next sequential ID, confirmed via Supabase
  MCP against `missions.mission_id` beforehand to make sure this wouldn't
  collide with the real `MSN-0361` minted earlier tonight. This consumed a
  real mission number as part of verifying the fix works end-to-end
  against live state, not a synthetic copy — `USS-TJR-MSN-0362` is now the
  stored counter value and should be treated as reserved/consumed.
- Ran `tools/id_counter_drift_check.py` for real, right now:

  ```
  Prefix  Stored    True Max  Status
  MSN     362       361       OK
  BREQ    10        0         OK
  DEC     0         0         OK

  OK — every known prefix's stored counter is at or above its true max.
  No drift; .id-counters.json is trustworthy right now.
  ```

  Exit code 0.

## Notes / open items (not in scope for this fix)

- **`knowledge/SUOC-Platform-Registry.md` isn't tracked in this git repo.**
  It exists in two local backup directories (`/root/USSTJROS.backup-
  20260719/` and `/opt/starship-endeavour.USSTJROS-backup-20260719/`) but
  `git log --all` shows zero commits for that path — it was never
  committed, the same failure mode that hit `.id-counters.json` tonight,
  on a file multiple existing tools' docstrings treat as canonical
  (`registry_staleness_check.py`, `registry_sync_check.py`). Worth a
  Captain/Chief-Engineer decision on whether to commit it from a backup or
  reconstruct it — flagging, not fixing, since it's outside this mission's
  scope and touches a platform-wide document other tooling depends on.
- BREQ/DEC repo-scanning has an inherent, disclosed limitation: without a
  live table to ground against (neither prefix has one — see above), a
  grep-based scan can only ever be as good as the text it's reading, and
  mock/demo data in non-test-named files (e.g. an old proof-of-concept
  module using `"DEC-015"` as example content) can register as a false
  signal. The `{4,5}`-digit tightening already closed the one real
  instance of this found live tonight. The failure direction is always
  safe (skips ahead unnecessarily, never collides) since it can only ever
  push the stored counter *up* to a higher number, never down past a real
  in-use ID. If BREQ/DEC ever get real sustained usage, the durable fix
  would be giving them a live table the way MSN has, not a smarter regex.
