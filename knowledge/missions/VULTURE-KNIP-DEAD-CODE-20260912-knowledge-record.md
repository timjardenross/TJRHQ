# Knowledge Record — Vulture + knip dead-code adoption, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0366 |
| Title | Vulture would have caught one thread of the commander_runtime.py/router.py cluster, not the cluster — the manual grep investigation was still doing real work a symbol-level scanner can't |
| Date | 2026-09-12 |
| Lesson | LL-162 |

## Outcome

Added two advisory (never merge-blocking) dead-code CI steps, both run for
real against the actual codebase before being wired in, not assumed clean:

- **Vulture** (2.16, `pip install vulture`) — a new `vulture` job in
  `.github/workflows/python-ci.yml`, `continue-on-error: true`, scanning
  `core/`, `intelligence/`, `platform-runtime/` at default (60%) confidence
  plus a repo-root `.vulture_whitelist.py` for two confirmed false
  positives (`__exit__(self, exc_type, exc_val, exc_tb)`'s mandatory
  context-manager signature in `core/infrastructure/mac-collector/db.py`
  and `core/infrastructure/vm-transfer/transfer_db.py`). Real run: 664
  findings. Full output and triage in `reports/vulture/`.
- **knip** (5.88.1) — added as an `lcars-portal` devDependency plus an
  `npm run deadcode` script, a new `deadcode` job in
  `.github/workflows/lcars-portal-ci.yml`, `continue-on-error: true`. A
  minimal `lcars-portal/knip.json` handles three confirmed false positives
  (two standalone scripts not meant to be imported, one service-worker
  asset registered by URL, not by import). Real run: 313 findings (31
  unused files, 1 unused devDependency, 104 unused exports, 173 unused
  exported types, 1 duplicate export). Full output and triage in
  `reports/knip/`.

Both tools found real, confirmed issues beyond noise — not just plausible
candidates, actually verified by reading the flagged code before writing
them up:

- Vulture caught a genuine latent bug: `platform-runtime/lib/
  mistral_agent_client.py`'s `call_agent()` accepts a `timeout_ms`
  parameter that is never used anywhere in the function body — not passed
  to the SDK call, not logged, despite its own docstring claiming
  otherwise. Callers configuring a custom timeout are silently ignored.
- Vulture also caught `platform-runtime/test_human_systems.py:300`'s
  `self.assertIn("numbness", out.lower()) if False else None` — a
  permanently-disabled assertion (`unsatisfiable 'ternary' condition`) that
  stopped actually testing the red-flag-language path it claims to cover.
  This is a class of bug the repo's existing grep-based tooling
  (`tools/verify_dead_code.py` and friends) structurally cannot find: it
  requires understanding control flow, not reference-counting.
- knip caught a real, deliberately-paused feature as a fully dead
  six-file cluster: `src/app/knowledge-workbench/_components/{LibraryView,
  LibraryKpis,BatchTriageBar,DocumentDetail,badges,types}` — confirmed by
  reading `knowledge-workbench/page.tsx`'s own comment ("Library ... pulled
  back to draft 2026-08-22, Captain directive ... hidden from view until
  it's ready"). It also caught `src/components/home/HomeScreen.tsx` as
  dead, confirmed by checking that every other repo mention of
  "HomeScreen" is a comment referencing the file by name, not an import.

### Would Vulture have caught the commander_runtime.py/router.py cluster? Tested directly, not assumed.

**Partially, and the miss is the more useful finding.** The mission brief
points at PR #96 (commit `19a6d2ba4`), which deleted
`platform-runtime/{commander_runtime.py,router.py}` and the six modules
they were the sole dispatch path into
(`mission_executor.py`, `specialist_registry.py`, `repository_awareness.py`,
`knowledge_retrieval.py`, `collaboration_engine.py`,
`runtime_event_logger.py`), after a manual, ad hoc full-repo grep confirmed
zero importers of `router.py`/`commander_runtime.py` from outside the pair
(documented in `platform-runtime/MODULE-MAP.md`).

To test this directly rather than take the mission brief's framing on
faith, we extracted the actual pre-deletion tree
(`git archive 19a6d2ba458e2e3081c280c39e235af4d65ce6ff^ -- platform-runtime`)
and ran the same Vulture command against it. Result (full output in
`reports/vulture/vulture-2026-09-12-commander-runtime-cluster-validation.txt`):
**exactly one finding anywhere in the eight-module cluster** —

```
platform-runtime/commander_runtime.py:561: unused function 'execute_commander_runtime' (60% confidence)
```

— which is the one true external entry point, previously called only by
`app.py` (already deleted in an earlier, separate commit). Vulture did
**not** flag `router.py`, `specialist_registry.py`,
`repository_awareness.py`, `knowledge_retrieval.py`, or
`collaboration_engine.py` at all, and did not flag `commander_runtime.py`
as a whole unreachable module — only that one named function.

The reason is structural, not a tuning problem: Vulture builds a flat
usage graph over whatever files you point it at and flags names
(functions/classes/variables/imports) with zero references *within that
graph*. It has no concept of "reachable from a real program entry point."
Because `router.py`, `commander_runtime.py`, and the BOT-0xx modules call
each other internally, every one of those internal calls counts as
"used" from Vulture's perspective — even though the whole eight-file
island had exactly zero callers from anywhere else in the repo. A human
(or agent) still has to notice the one flagged unused function, ask "who
calls `execute_commander_runtime`?", find the answer is "nobody, app.py is
gone", and then pull that thread through the rest of the cluster — which
is precisely the manual-grep step the mission brief references and exactly
what `tools/verify_dead_code.py` already automates *per path, on demand*,
just not automatically on every PR across the whole tree.

knip, tested on the frontend side, does not have this blind spot for its
own domain: it does real whole-file reachability analysis from Next.js's
declared route entry points (`page.tsx`/`layout.tsx`/`route.ts`/etc, via
its built-in Next.js plugin), which is exactly why it caught the entire
six-file `knowledge-workbench` "Library" cluster as unused files, not just
one buried unused function inside it. That is the direct, evidence-backed
contrast this record exists to capture: a symbol-usage scanner (Vulture,
in its default mode) sees a mutually-referencing dead island as "all used";
a module-reachability scanner with real entry-point knowledge (knip, for
this stack) sees the same shape of island as "all dead."

## Lesson

"Would tool X have caught bug/dead-code Y" is answerable with evidence, not
just plausibility — extracting the actual historical tree at the commit
before the fix and re-running the tool against it is cheap (one
`git archive` call) and turns a hand-wavy "probably" into a real yes/no
with a line number attached. Here it turned what would have been a
too-generous claim ("Vulture would have caught this") into a more accurate
and more useful one ("Vulture would have pointed at the one thread worth
pulling, not rolled up the whole cluster for you").

The deeper, generalizable lesson: default-mode Vulture (and static
per-symbol dead-code scanners generally) cannot detect an island of
mutually-referencing code whose only problem is that nothing *outside* the
island calls in — it can only flag names unused *within whatever scope
you feed it*. Tools built with real entry-point/reachability knowledge of
their target framework (knip's Next.js plugin knowing every `page.tsx` is
a live route; a Python equivalent would need to know its own real entry
points — CLI `if __name__ == "__main__"` scripts, WSGI/ASGI app objects,
Slack/Telegram bot dispatch tables, systemd `ExecStart` targets) can catch
a whole orphaned cluster in one shot. Vulture cannot be configured into
having this, because it fundamentally doesn't model "entry point" as a
concept — this is a property of the tool, not a confidence-threshold or
whitelist setting to tune away.

## Future Guidance

- Treat Vulture as complementary to, not a replacement for,
  `tools/verify_dead_code.py`: Vulture is good at *fast, automatic, every-PR*
  detection of individual unused symbols (imports, dead parameters, an
  accidentally-disabled assertion) that nobody would think to manually grep
  for; `verify_dead_code.py` is good at *authoritative, on-demand*
  verification of "is this whole path actually dead" including non-Python
  signals (systemd units, crontab) that Vulture cannot see at all. Keep
  running both — don't retire the manual-investigation tooling because
  Vulture is now in CI.
- When Vulture flags a single unused top-level function in a file that
  looks like a dispatch/integration layer (a name like
  `execute_X_runtime`, `handle_X`, `dispatch_X`), treat that as a prompt to
  run `tools/verify_dead_code.py` on the whole containing module, not just
  delete the one function — that single flagged symbol is often the
  visible tip of exactly this kind of orphaned-island cluster.
- If dead-code coverage needs to catch orphaned Python module clusters
  automatically (not just via the on-demand script), the actual gap to
  close is a real-entry-point/reachability-aware checker for this repo's
  own entry points (Telegram bot dispatch tables, `platform-runtime`'s
  now-removed Slack dispatch, systemd `ExecStart` scripts) — not a Vulture
  confidence tweak. That is future work, not something this stream's scope
  covered; flagging it here so it isn't lost.
- Both `.vulture_whitelist.py` and `lcars-portal/knip.json` should stay
  small and evidence-backed — every entry in both files, as of this
  commit, was added only after reading the flagged code and confirming a
  real false positive (documented inline in each file and in
  `reports/vulture/README.md` / `reports/knip/README.md`). Resist the urge
  to pre-emptively widen either file to silence noise before someone has
  actually looked at what's being silenced.
