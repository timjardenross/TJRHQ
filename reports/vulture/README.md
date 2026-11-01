# Vulture dead-code scan — 2026-09-12

Real run, real output. Vulture 2.16, `pip install vulture`, default confidence
(60%), against the actual repo tree — no synthetic examples.

```
vulture core/ intelligence/ platform-runtime/ .vulture_whitelist.py --min-confidence 60
```

Files in this directory:

- `vulture-2026-09-12-full-output.txt` — full output against the current
  repo (664 findings, after the two confirmed-false-positive whitelist
  entries in `.vulture_whitelist.py` at repo root are applied).
- `vulture-2026-09-12-commander-runtime-cluster-validation.txt` — full
  output from a **separate, historical validation run** against the
  `platform-runtime/` tree as it existed at commit `19a6d2ba4^` (one commit
  before the BOT-0xx cluster — `commander_runtime.py`, `router.py`,
  `mission_executor.py`, `specialist_registry.py`, `repository_awareness.py`,
  `knowledge_retrieval.py`, `collaboration_engine.py`,
  `runtime_event_logger.py` — was deleted in PR #96). This is the concrete
  test of whether Vulture would have caught the cluster the mission brief
  references. See "Commander-runtime/router cluster: would Vulture have
  caught it?" below and the knowledge record for the full analysis.

## Current-repo findings: 664 total

| Confidence | Count | Kind |
|---|---|---|
| 100% | 19 | unused variable (mostly real: unused test fixture args, unused locals, one unsatisfiable ternary) |
| 90% | 8 | unused import |
| 60% | 637 | unused variable / function / method / attribute / property / class |

By directory: `platform-runtime/` 373, `core/` 222, `intelligence/` 69.

The 60%-confidence bucket is dominated by `unused variable` (326 total) and
`unused attribute`/`unused method`/`unused property` (161 combined) — this is
Vulture's known noisy tier (tuple-unpacking placeholders, dataclass/Pydantic
fields only ever set via `**kwargs` or reflection, protocol methods called
polymorphically). We did **not** hand-triage all 637 of these; that is real,
ongoing human work the advisory CI step exists to surface incrementally, not
a one-time backlog to clear. What follows is triage of the higher-confidence
tier (100%/90%, 27 findings) plus the two whitelisted false positives, which
is where the true-positive rate is highest.

### Confirmed true positives (worth a follow-up ticket)

- **`platform-runtime/lib/mistral_agent_client.py:105`** — `call_agent()`
  accepts a `timeout_ms: int = 60_000` parameter. Verified by reading the
  full function body: it is never passed to the SDK call, never used to
  bound `time.monotonic()` elapsed time, and never logged — despite the
  function's own docstring claiming "used for log." **This is a real latent
  bug**: callers who pass a custom `timeout_ms` get silently ignored,
  always getting whatever the underlying SDK's default timeout is.
- **`platform-runtime/test_human_systems.py:300`** — `unsatisfiable
  'ternary' condition`. The line is
  `self.assertIn("numbness", out.lower()) if False else None` — a real
  assertion permanently disabled by a hardcoded `if False`. This test
  silently stopped checking the "numbness" red-flag output years/months ago
  and nobody would know from the test suite passing. This is exactly the
  class of bug the repo's existing tooling (grep-based, path-existence
  checks) cannot find at all — it requires understanding control flow, not
  just references.
- **`intelligence/ranking/content_ranker.py:23`** and
  **`intelligence/ranking/ranker.py:21`** — `import math` unused in both
  files (confirmed by reading each file; no `math.` usage anywhere).
  Harmless but real dead import, likely copy-pasted between the two ranker
  variants.
- **`intelligence/brief/llm_provider.py:31`** —
  `MISTRAL_SUMMARY_AGENT_ID`/`MISTRAL_SUMMARY_AGENT_VERSION` imported but
  unused in this file.
- **`platform-runtime/lib/captains_inbox_events.py:21`** —
  `extract_first_url` imported from `lib.captains_inbox_capture` but never
  referenced in this file.
- **`core/voice/tts_chatterbox.py:43`** — `import torch` unused.
- Five more unused-parameter findings worth a look but not confirmed as
  bugs the way `timeout_ms` was (parameter accepted, never read in the
  function body — may be intentional API-compatibility placeholders):
  `adaptive_routing_service.py:192` (`selected_provider`),
  `lib/delivery/execution.py:82` (`approver`),
  `lib/investigation/registry.py:133` (`question_prefix`),
  `lib/officers/officer_context.py:212` (`cycle_ctx`),
  `core/coordination/commander_memory_adapter.py:38` (`research_summary`).

### Confirmed false positives (handled via `.vulture_whitelist.py`)

- **`core/infrastructure/mac-collector/db.py:71`** and
  **`core/infrastructure/vm-transfer/transfer_db.py:78`** —
  `exc_type`/`exc_val`/`exc_tb` on `__exit__(self, exc_type, exc_val,
  exc_tb)`. This is the mandatory Python context-manager protocol
  signature; both implementations legitimately ignore the exception detail
  and just call `self.close()`. Whitelisted at the repo root in
  `.vulture_whitelist.py` (not preemptively — added only after confirming
  by reading both call sites that this is the dunder-protocol pattern, not
  a wrong number of args).

### Noted-but-not-whitelisted false-positive pattern

- **`core/coordination/number_one_exporter.py:82,90`** — `import ... as
  _supabase_configured` / `_persist_readiness` at 90% confidence. Read in
  context: these are inside `try: import X as Y ... except ImportError:` blocks
  used purely to probe whether an optional dependency is importable
  (`_LESSONS_AVAILABLE = True` is set as a side effect of the import
  succeeding; the bound name itself is never called). This is a real,
  recognizable pattern in this codebase but a one-off in this file, so it
  was left as a documented false positive here rather than added to the
  repo-wide whitelist (whitelisting `_supabase_configured`/`_persist_readiness`
  by name would be too narrow to matter and the pattern doesn't recur
  elsewhere in current findings).

## Commander-runtime/router cluster: would Vulture have caught it?

**Partially — and the gap is instructive.** See the knowledge record
(`knowledge/missions/VULTURE-KNIP-DEAD-CODE-20260912-knowledge-record.md`)
for the full writeup. Short version: run against the pre-deletion snapshot
(`vulture-2026-09-12-commander-runtime-cluster-validation.txt`), Vulture
flagged exactly one symbol in the whole eight-module cluster —
`platform-runtime/commander_runtime.py:561: unused function
'execute_commander_runtime'` (60% confidence) — the one true external entry
point, which only the already-deleted `app.py` had ever called. It did
**not** flag `router.py`, `specialist_registry.py`,
`repository_awareness.py`, `knowledge_retrieval.py`, or
`collaboration_engine.py` at all, because those modules call each other
internally; Vulture's static usage graph sees those internal calls as
"used" and has no concept of whole-module reachability from a real program
entry point. A human (or agent) still has to notice the one flagged
function, ask "who calls this?", and pull the thread through the rest of
the cluster the way the original manual grep investigation did.
