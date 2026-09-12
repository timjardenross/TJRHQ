# Knowledge Record — Semgrep OSS CLI adoption, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0366 |
| Title | Registry rulesets need a network egress allowlist entry this sandbox doesn't have — custom rules don't, and found 48 real hits on the first run |
| Date | 2026-09-12 |
| Lesson | LL-155 |

## Outcome

Added Semgrep OSS CLI as a new, advisory (non-blocking) SAST layer —
net-new to this repo, nothing here ran Semgrep before this stream. Four
pieces landed:

1. **`.semgrep.yml`** (repo root) — three custom `custom.rls.*` rules
   targeting real RLS-adjacent risk patterns found by grepping this actual
   codebase for `service_role`/`SUPABASE_SERVICE_ROLE_KEY` (169 files
   matched) rather than inventing hypothetical Supabase misuse patterns:
   - `custom.rls.postgrest-filter-string-injection` (TS/JS) — a
     `.or()`/`.ilike()`/`.filter()`/`.match()` PostgREST filter built from a
     template literal with an interpolated value (PostgREST's filter
     syntax is itself a small query language; an unescaped value can widen
     or reshape the filter). Modeled directly on real code in
     `lcars-portal/src/app/api/health-osint/library/route.ts` and
     `lcars-portal/src/lib/ask.ts`.
   - `custom.rls.service-role-key-client-js` (TS/JS) — a Supabase client
     built with `SUPABASE_SERVICE_ROLE_KEY` inline
     (`createClient(url, process.env.SUPABASE_SERVICE_ROLE_KEY)`), which
     bypasses RLS on every table unconditionally — advisory, prompting a
     human to confirm the route re-implements whatever authorization RLS
     would otherwise have provided. Modeled on the ~15 Next.js API routes
     under `lcars-portal/src/app/api/**` that build this client inline,
     and on `lcars-portal/src/lib/supabase-service-role.ts`'s own
     docstring, which already documents this exact bypass for
     `core_events`.
   - `custom.rls.service-role-key-client-py` (Python) — the same pattern
     for `create_client()` calls fed a `SUPABASE_SERVICE_ROLE_KEY` read
     from the environment. Modeled on `tools/supabase/client.py`'s
     `CommanderSupabaseClient`, and cross-referenced against
     `telegram-bots/xo/scoped_supabase.py` / `.claude/skills/bot-reviews/
     fixes-2026-08-09/xo-bot-service-role-decision.md`, which already
     document a real, reviewed decision process for exactly this
     trade-off on a different bot (kept `service_role`, documented why,
     specced but did not implement a narrower scoped-role alternative).
   Registry rulesets (`p/python`, `p/javascript`, `p/typescript`,
   `p/security-audit`) are referenced from CI via separate `--config`
   flags, not pulled into this file — see the "what didn't fully work"
   section below for why, and for the fact that this specific combination
   was never actually verified end-to-end.

2. **`.github/workflows/python-ci.yml`** — new `semgrep` job, added
   alongside the existing `actionlint` job (same shape: runs once over the
   whole tree, not per-matrix-directory like `test`). `continue-on-error:
   true`; installs a pinned `semgrep==1.177.0` via `pip`; runs
   `semgrep scan` with the four registry configs plus `.semgrep.yml`;
   uploads the JSON output as a build artifact. No `SEMGREP_APP_TOKEN`, no
   `semgrep ci`, no login, no secret of any kind — pure OSS-CLI mode, per
   the mission's own scope constraint. `permissions: contents: read` is
   inherited from the workflow-level block already in this file (not
   redeclared per-job, matching how `actionlint` does it).

3. **`reports/semgrep/20260912-060349-findings.md`** (+ the paired
   `.json` of the same run) — the real, local output of
   `semgrep scan --config=.semgrep.yml --metrics=off
   --disable-version-check .` against this repo right now: 48 findings,
   3 rules, 2928 files tracked by git / 1376 actually scanned, exit 0,
   ~7.7s. Every finding was individually triaged (file/line
   hand-verified, not just counted) — see that report for the full
   breakdown. Headline: 15/15 of the JS service-role hits do call
   `requireSession()` before constructing the client (verified per-file,
   line-number-ordered); 13/18 of the Python hits are one-shot batch
   tooling where `service_role` is the correct, intended choice; the
   remainder (5 always-running Python services, and the 15 PostgREST
   filter-injection hits, none escaped) are flagged as real follow-up
   candidates, explicitly out of scope for this CI-wiring mission to fix.

4. This record.

## Lesson

**A sandboxed agent's outbound egress allowlist is scoped to package
registries, not to every service a tool might phone home to — and a
security scanner phoning home is not always obvious from its name.**
`pip install semgrep` worked immediately (pypi.org is allowlisted). Every
attempt to actually *use* a Semgrep registry config
(`--config=p/python`, `--config=auto`, and even a fully local
`--config=.semgrep.yml` combined with `--validate`, which turned out to
call `semgrep.dev/c/p/semgrep-rule-lints` for a rule-lint check even
though the config itself is 100% local) failed with the exact same
proxy-level `connect_rejected`/`403` on the CONNECT tunnel to
`semgrep.dev` — confirmed via `curl .../__agentproxy/status`, which
lists an explicit `noProxy` allowlist covering `pypi.org`,
`files.pythonhosted.org`, `registry.npmjs.org`, `jsr.io`, `index.crates.io`,
`proxy.golang.org`, and Anthropic's own API hosts, and nothing else.
`semgrep.dev` was never going to be reachable no matter how the CLI was
invoked, because the block is at the network-policy layer, not something
any CLI flag (`--metrics=off`, `--disable-version-check`, offline mode)
can route around — those flags stop semgrep from *trying* certain calls,
but the ones needed to actually pull a registry ruleset are unavoidable
by design (that's what "a hosted registry ruleset" means).

Separately, and worth remembering on its own: **`semgrep scan` can hang
past a reasonable timeout on unrelated background network calls even when
the scan itself is instant.** The very first full-repo run
(`--config=.semgrep.yml` only, no registry config, no `--validate`) took
over 120s and was killed by an external `timeout`, even though the JSON
output it had already written was complete and valid (33 real findings,
confirmed by loading the file) — the hang was a post-scan network call
(observed proxy-log entries for `semgrep.dev` and, oddly,
`events.telemetry.data.nvidia.com`) that `--metrics=off` alone doesn't
suppress. Adding `--disable-version-check` fixed it outright: the same
scan (grown to the full 48-finding run) completed cleanly in 7.7s, exit
0. Anyone re-running this CLI standalone (not through the CI job, which
already carries this flag) should carry `--disable-version-check` too, or
budget for the hang.

## Future Guidance

1. **The first real CI run of the new `semgrep` job needs to be watched,
   not assumed clean.** This mission could not verify from its sandbox
   that a GitHub-hosted Actions runner actually reaches `semgrep.dev` for
   the four registry configs — a reasonable expectation (GitHub-hosted
   runners have normal unrestricted egress), but genuinely untested here.
   If that step's registry fetch fails in real CI with the same
   `connect_rejected`/proxy-style error, that means GitHub Actions' own
   network policy (or an org-level egress control on the runner) is the
   actual blocker, not a bug in this job — check that policy rather than
   re-debugging the YAML.
2. **Before treating any future Semgrep CI failure as "the tool is
   broken," check whether the failure is really a blocked call to
   `semgrep.dev`** (registry fetch, version check, telemetry, or the
   rule-lint check `--validate` makes) versus a genuine parse/rule error
   — the error text looks similar (a Python traceback ending in
   `ProxyError`/`ConnectionError`) but the fix is completely different
   (network policy vs. a rule bug).
3. **The 15 `custom.rls.postgrest-filter-string-injection` hits and the 5
   always-running-service `custom.rls.service-role-key-client-py` hits
   from the first real scan (see `reports/semgrep/
   20260912-060349-findings.md`) are real, un-triaged-to-completion
   findings, not resolved by this mission.** This stream's scope was CI
   wiring, deliberately not an RLS remediation pass — but they should not
   be allowed to just sit in a build artifact forever. Worth a follow-up
   ticket, most usefully the `lcars-portal/src/lib/ask.ts` filter-string
   cluster (5 of the 15, all against tables reachable from a
   user-typed search term) since that one has no RLS backstop question at
   all — it's a straightforward "escape or parameterize the filter"
   fix regardless of any authorization-model discussion.
4. **`.semgrep.yml`'s three custom rules only cover the `create_client()`
   / template-literal-`.or()` call shapes actually observed in this repo
   today — they do not cover every way a service_role key or an
   unsanitized filter could reach a query.** Documented explicitly in the
   findings report: `core/health/supabase_client.py` reads
   `SUPABASE_SERVICE_ROLE_KEY` and uses it for raw `urllib` calls with an
   `Authorization: Bearer` header, which is the same underlying risk but
   isn't caught by `custom.rls.service-role-key-client-py` (that rule
   only matches `create_client()`). A more general taint-mode rule
   (any `SUPABASE_SERVICE_ROLE_KEY`-derived value flowing into an
   outbound HTTP call) would close this gap properly; judged out of scope
   for a first pass and flagged rather than silently left uncovered.
