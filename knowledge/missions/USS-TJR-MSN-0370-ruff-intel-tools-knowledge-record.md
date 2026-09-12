# Knowledge Record — USS-TJR-MSN-0370 (Ruff Manual-Judgment Triage — intelligence/ + tools/)

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0370 |
| Title | Ruff manual-judgment triage, intelligence/ + tools/ (follow-up to MSN-0369) |
| Scope | `intelligence/` and `tools/` directories only — `core/`, `platform-runtime/`, `telegram-bots/` worked in parallel by other agents/worktrees |
| Date | 2026-09-12 |
| Branch | `msn-0370-ruff-intel-tools` |
| Follows | USS-TJR-MSN-0369 (ruff autofix pass — mechanical fixes only) |

## Outcome

**Starting count: 617 findings. Ending count: 0 findings.** Every finding in
`intelligence/` and `tools/` was either fixed with a real code change or
suppressed with an inline `# noqa: <CODE> - <reason>` comment explaining the
judgment. Nothing was mechanically globbed without reading the surrounding
code — every BLE001/S110/S112/DTZ site was read in context before deciding
fix vs. suppress.

Verified clean: `ruff check intelligence tools --statistics` (run from the
branch tip) prints nothing and exits 0.

## Breakdown by rule family (all resolved)

| Rule(s) | Count at mission start | Treatment |
|---|---|---|
| BLE001 (blind except) | 284 | ~15 real fixes (added logging where genuinely silent, or a real missing behavior); rest suppressed with per-site reasons after reading context |
| EXE002 (shebang missing) | 95 | 79 files `chmod -x` (no `__main__`, never meant to run standalone — confirmed via grep for invocation sites); 16 files got a real shebang added (`__main__` present but shebang missing) |
| DTZ005 (naive `datetime.now()`) | 51 | Real fixes: `datetime.now(timezone.utc)` where safe, `datetime.now(_AEST)`/local-aware equivalents where business-date semantics required it; 2 sites suppressed (deliberate host-local-time fallback in a defensive-only except) |
| S110 (try/except/pass) | 23 | Real fixes: added logging (debug for best-effort probes, warning for job-boundary catches) at every genuinely-silent site; a few pre-logged sites got noqa only |
| DTZ003 (`datetime.utcnow()`) | 22 | 100% real fix: `datetime.now(timezone.utc)` (same instant, explicit tz) — always safe, no judgment needed |
| EXE001 (shebang present, not executable) | 15 | 100% mechanical: `chmod +x` after confirming each has a real `__main__` entrypoint |
| DTZ011 (`date.today()`) | 15 | Real fixes: `datetime.now(_AEST).date()` for AEST-business-date logic (captains_brief.py), UTC for DB-timestamp-matching logic (llm_cost_governance.py, external_fetch_budget.py), `datetime.now().astimezone().date()` where host-local semantics were the pre-existing (correct) intent |
| RUF013 (implicit Optional) | 13 | 100% mechanical: `T = None` → `T \| None = None`, no behavior change |
| PLW1510 (subprocess.run no check=) | 13 | 100% real fix: added explicit `check=False` — every site either manually inspects `.returncode` itself or treats a non-zero exit as a normal outcome (e.g. `git grep`'s exit 1 = no matches); `check=True` would have broken these |
| F841 (unused variable) | 13 | Mostly mechanical removal; 2 real fixes found while triaging — see "Real bugs found" below |
| RUF012 (mutable class default) | 10 | 100% mechanical: `ClassVar[...]` annotation after confirming none of the containing classes are `@dataclass` |
| S112 (try/except/continue) | 9 | Same treatment as S110 |
| ISC004 (implicit string concat in collection) | 8 | 100% mechanical: wrap in parens |
| DTZ007 (naive strptime) | 7 | 2 real fixes (attach `tzinfo=timezone.utc` where source format is UTC-only by construction); 3 sites suppressed as a disclosed **known gap** (source feeds carry no offset info at all — flagged, not guessed); 2 sites suppressed as false-risk (result truncated to `.date()` or offset applied immediately after) |
| RUF059 (unused unpacked variable) | 6 | 100% mechanical (`ruff --fix --unsafe-fixes`) |
| PIE810 (multiple startswith) | 4 | 100% mechanical: merge into one `.startswith((...))` call |
| F821 (undefined name) | 4 | 2 real fixes (quoted forward-ref type annotations needed `if TYPE_CHECKING: import ...`); 1 real bug fix (a literal `PYEOF` heredoc terminator leftover in `tools/integrate_lessons.py`, removed); 1 covered by the TYPE_CHECKING fix pattern |
| SIM102 (collapsible if) | 3 | 100% mechanical: merge nested `if` into one `and` condition |
| G201 (log.error+exc_info → log.exception) | 3 | 100% mechanical, but exposed follow-on TRY401 (redundant exc in the message) and F841 (now-unused `exc` binding) at 3 sites, fixed alongside |
| E722 (bare except) | 2 | Real fix: narrowed to `(json.JSONDecodeError, ValueError)` — the only exceptions `json.loads` on a string can raise |
| PERF102 (dict.items() unused key) | 2 | 100% mechanical: `--fix --unsafe-fixes` |
| N999 (invalid module name) | 2 | **Not fixed** — flagged instead. `tools/health-osint/` (hyphenated dir) is referenced by path across cron/systemd units; renaming is a real cross-cutting production-invocation-risk change, out of scope for a lint-triage mission. Suppressed via `# noqa: N999` in both `__init__.py` files with a comment explaining why. |
| FURB192 (sorted→min) | 2 | 100% mechanical: `--fix --unsafe-fixes` |
| C401 (generator→set comprehension) | 2 | 100% mechanical: `--fix --unsafe-fixes` |
| SIM113/SIM118/PLW1508/PYI034/PLW0127/RUF046/RUF015/RUF022/B018 | 1 each | Mechanical fixes, mostly via `--fix --unsafe-fixes`; PLW0127 was a genuine leftover self-assignment (`cps230 = cps230`) from an incomplete earlier edit |

## Real bugs found and fixed while triaging (not just lint satisfaction)

1. **`intelligence/brief/correlation_synthesis.py`** — `r_value` and
   `sample_size` were computed per correlation insight but silently dropped
   before ever reaching the rendered markdown line (F841 caught the dead
   assignment). The Captain-facing brief was showing correlation findings
   with no coefficient or sample size backing them. Fixed: now rendered as
   `[CONF, r=.., n=..]`.
2. **`tools/supabase/test_msn_0013bcd.py`** — `initial_count` was computed
   but never asserted, even though the preceding comment says "First review
   should include all docs." Added the matching `assertEqual` — a genuine
   missing test check, not just an unused variable.
3. **`tools/integrate_lessons.py`** — a literal `PYEOF` heredoc terminator
   was left in the file after `if __name__ == "__main__": main()`, a
   leftover artifact from however the file was originally generated. Not
   valid trailing syntax; removed (this is what ruff's B018
   useless-expression + F821 undefined-name were actually flagging).
4. **`intelligence/audit/brief_coherence.py` / `enrichment_validation.py`**
   — bare `except:` narrowed to the real exception types `json.loads` can
   raise, and a genuine leftover self-assignment (`cps230 = cps230`, dead
   code from an incomplete prior edit) removed.

## Known gaps flagged, not fixed (deliberately — would need a policy/data decision, not a lint fix)

1. **`intelligence/content_intelligence_service.py`** — `score_and_persist()`
   loads `_load_approved_source_ids()` (the `terms_reviewed=true` governance
   gate) but never applies the result to filter `events`. `content_signals`
   can currently be written from sources that haven't cleared terms review.
   This is a real governance gap, not a lint issue — flagged in place with a
   `KNOWN GAP` comment + `# noqa: F841`, not silently fixed by guessing the
   intended filter logic (which would be a real behavior change outside
   this mission's scope).
2. **`intelligence/ingestion/emergency_alert_adapters/act_esa.py` and
   `base.py` (NSW RFS / VIC Emergency DMY parsers)** — these source feeds
   carry **no timezone/offset information at all** in their raw strings
   (unlike `bom_warnings.py`, which has a recoverable offset abbreviation
   and was fixed properly for a real production bug on 2026-08-27). Flagged
   with `KNOWN GAP` comments and `# noqa: DTZ007`, not guessed — a wrong
   guess here (assuming UTC when the true source convention is unverified
   local time) could repeat exactly the class of bug bom_warnings.py's own
   history describes (a real alert landing 10 hours off).
3. **`tools/health-osint/` directory name** — hyphenated, invalid Python
   module name (N999). Not renamed; referenced by path across
   cron/systemd units and other scripts. A rename is a real cross-cutting
   change with production-invocation risk, explicitly out of scope for a
   ruff-triage mission.

## Judgment calls worth double-checking (not wrong, but a human should know)

- **`intelligence/ingestion/external_fetch_budget.py`** — billing-cycle
  "today" fallback changed from ambiguous host-local `date.today()` to
  explicit UTC. This changes the default cycle-boundary day for
  firecrawl/brightdata billing-cycle tracking when the `today` param isn't
  passed explicitly. Chosen because vendor billing cycles reset on a fixed
  calendar boundary, not host wall time, but this was a genuine behavior
  change (previously host-local), not purely cosmetic.
- **`intelligence/governance/llm_cost_governance.py`** — `_get_daily_spent`'s
  "today" changed from host-local to UTC to match `llm_daily_costs.cost_date`
  (computed by Postgres as `current_date`, effectively UTC on this DB).
  Same category of change as above — a real, reasoned behavior fix, not
  cosmetic.

## Test verification

No test framework was pre-installed in this environment; a venv with
pytest was created ad hoc (`/tmp/msn0370-venv`). Most test files in
`intelligence/`/`tools/` import optional heavy dependencies
(`dotenv`, `supabase`, `requests`, `mistralai`, `defusedxml`) not installed
in this sandbox, so full test execution wasn't possible end-to-end.
Verification instead relied on:
- `python3 -m py_compile <file>` on every single file touched, across all
  17 commits — zero syntax/compile failures.
- Targeted `ruff check <file> --select <RULE>` after every edit to confirm
  the specific finding cleared without introducing a new one (this caught
  several second-order findings: F401 unused imports after removing a
  `date` usage, I001 unsorted imports after adding `ClassVar`, TRY401 +
  F841 after `log.exception()` conversions — all fixed in the same or a
  following commit).
- One test file (`intelligence/analysis/test_shadow_mode_scoring.py`) ran
  successfully under the ad hoc venv (`no tests ran` — it didn't cover the
  touched module, but confirmed the import chain works).

## Commits (17 total on `msn-0370-ruff-intel-tools`, chronological)

1. DTZ family part 1 — `datetime.utcnow()` → `datetime.now(timezone.utc)`
2. DTZ family part 2 — remaining DTZ005/007/011 + one S110 fix found along the way
3. S110/S112 — all try/except/pass/continue in intelligence/+tools/
4. EXE001/EXE002 — shebang/executable-bit classification for all 110 findings
5. F841/RUF059 — unused variables, including the 2 real bugs above
6. RUF013/RUF012/PLW1510 — implicit Optional, mutable class defaults, subprocess check=
7. Misc long tail — ISC004, PIE810, F821, SIM102, G201, E722, PERF102, N999, FURB192, C401, and 9 more single-occurrence rules (down to BLE001-only backlog)
8–17. BLE001, ten sequential commits working file-by-file from largest (scheduler.py, 42 findings) down to the final single-count files, ending at 0

Every commit is `SKIP=ruff-check,bandit` per `.pre-commit-config.yaml`'s
documented convention, since editing a handful of lines in a large file
that still carried unrelated pre-existing findings (in scope for a *later*
commit in this same mission) would otherwise block every intermediate
commit. Gitleaks and detect-secrets were never skipped and passed on every
commit.

## What's left

Nothing in `intelligence/` or `tools/` — confirmed 0 findings. The repo
overall still has ruff debt in `core/`, `platform-runtime/`,
`telegram-bots/`, and other directories, which per the mission brief were
being worked by parallel agents/worktrees on this same USS-TJR-MSN-0370
mission and are out of this branch's scope.
