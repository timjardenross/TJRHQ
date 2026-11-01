# Module Map

Overview of runtime modules and responsibilities.

## Slack Commander removal — confirmed dead code (2026-09-09)

The Slack Commander bot was removed platform-wide: `app.py` and `commander_bridge.py`
are deleted from the repo. `commander_runtime.py` and `router.py` are still present on
disk but are themselves dead — a full-repo grep (both `import`/`from ... import` forms
and a check for importlib/dynamic loading) found zero importers of either file anywhere
outside each other.

Because `commander_runtime.py` and `router.py` were the only dispatch path into the
BOT-008/010/011/012/013 cluster, that whole cluster plus `runtime_event_logger.py` is
now confirmed dead code with zero live callers repo-wide:

| Module | BOT ID | Live callers | Tests | Status |
|---|---|---|---|---|
| `mission_executor.py` | BOT-013 | none (only `router.py`, `commander_runtime.py`, both dead) | `test_intelligence_loop.py` (tests internals only) | **Dead** |
| `specialist_registry.py` | BOT-010 | none (only `mission_executor.py`, `collaboration_engine.py`, `router.py`, `commander_runtime.py`, all dead) | none | **Dead** |
| `repository_awareness.py` | BOT-008 | none (only `router.py`, `commander_runtime.py`, both dead) | `tests/test_repository_awareness_source_truth.py` | **Dead** |
| `knowledge_retrieval.py` | BOT-011 | none (only `mission_executor.py`, `router.py`, `commander_runtime.py`, all dead) | none | **Dead** |
| `collaboration_engine.py` | BOT-012 | none (only `commander_runtime.py`, dead) | none | **Dead** |
| `runtime_event_logger.py` | — | none (only `commander_runtime.py`, dead) | none | **Dead** |

`commander_runtime.py` and `router.py` are recommended for deletion too, since they have
no live callers themselves. Proposed for deletion once the user confirms: the six modules
above, `commander_runtime.py`, `router.py`, and the two now-dead tests
(`test_intelligence_loop.py`, `tests/test_repository_awareness_source_truth.py`).

Everything below this section describes the pre-removal architecture; it is retained for
historical context only and no longer reflects a live dispatch path.

## Runtime Entry (historical — removed)

- `app.py` - Slack event entry point. Runtime dispatch order is GitHub issue generation, mission registry, specialist registry, repository awareness, knowledge retrieval, collaboration, then normal Commander response.
- `commander_runtime.py` - Commander Runtime v1.0 integration layer. Owns intent classification, runtime context, BOT path selection, BOT invocation, mission logging, runtime event logging and graceful fallback handling.
- `router.py` - Mission-domain and specialist routing hints for Slack requests.
- `llm.py` - Lazy OpenAI client wrapper for normal Commander and issue-generation responses. Provides safe availability checks and non-throwing calls for runtime fallback paths.
- `prompt_loader.py` - Loads local Commander context from command, registry, memory and specialist documents.
- `runtime_event_logger.py` - CRT-style JSONL event logger with safe redaction and non-throwing emit helpers.

## Commander Runtime Capabilities (historical — removed)

- `repository_awareness.py` - BOT-008 repository-aware answers using local repository catalogue, source-of-truth and knowledge index documents. Refuses secret paths and degrades when expected files are missing.
- `mission_registry.py` - BOT-009 mission creation, status lookup, active/completed listings and search using the existing mission logger/index format plus `missions/Mission-Registry.md` where available.
- `specialist_registry.py` - BOT-010 registry-backed specialist discovery, active/future crew listings, routing recommendations and routing explanations.
- `knowledge_retrieval.py` - BOT-011 local markdown retrieval engine. Classifies knowledge domains, selects focused source documents, loads safe context, reports confidence and refuses secret-file requests.
- `collaboration_engine.py` - BOT-012 simulated multi-specialist collaboration engine. Classifies mission type, selects a specialist team, assigns an owner, generates profile-based viewpoints, consolidates recommendations, captures risks and next actions.
- `knowledge/frameworks/design-review/` - Design review frameworks for UX, product, information architecture, research and USS TJR design principles.
- `mission_executor.py` - BOT-013 synchronous mission execution orchestrator. Creates execution plans, assigns owners and specialists, identifies knowledge sources, updates status, summarizes progress and closes missions.
- `missions/analytics/` - Mission dashboard framework for mission age, completion rate, blocked mission detection, owner workload and mission history reporting.

## Runtime Event Logging (historical — removed)

- `logs/runtime-events.jsonl` - Structured JSONL runtime event log written by `runtime_event_logger.py`. Events avoid full request text and secret values.

Note: `mission_registry.py` (BOT-009) is NOT part of this dead cluster — it is still
imported by `test_mission.py`, and `mission_logger.py` remains alive via
`mission_manager.py`. `lesson_capture.py` remains alive via
`core/coordination/number_one_exporter.py` and `core/knowledge/outcome_capture.py`. These
were out of scope for this investigation and were not further verified end-to-end.

## Existing Support Modules

- `mission_logger.py` - Existing append-only mission log writer. Preserved for regression compatibility.
- `mission_manager.py` - Earlier mission-history helper retained for compatibility, superseded at runtime by `mission_registry.py`.
- `github_issue_formatter.py` - GitHub issue prompt formatter.
- `github_awareness.py` - GitHub repository awareness helper.
