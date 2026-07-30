# Module Map

Overview of runtime modules and responsibilities.

## Runtime Entry

- `app.py` - Slack event entry point. Runtime dispatch order is GitHub issue generation, mission registry, specialist registry, repository awareness, knowledge retrieval, collaboration, then normal Commander response.
- `commander_runtime.py` - Commander Runtime v1.0 integration layer. Owns intent classification, runtime context, BOT path selection, BOT invocation, mission logging, runtime event logging and graceful fallback handling.
- `router.py` - Mission-domain and specialist routing hints for Slack requests.
- `llm.py` - Lazy OpenAI client wrapper for normal Commander and issue-generation responses. Provides safe availability checks and non-throwing calls for runtime fallback paths.
- `prompt_loader.py` - Loads local Commander context from command, registry, memory and specialist documents.
- `runtime_event_logger.py` - CRT-style JSONL event logger with safe redaction and non-throwing emit helpers.

## Commander Runtime Capabilities

- `repository_awareness.py` - BOT-008 repository-aware answers using local repository catalogue, source-of-truth and knowledge index documents. Refuses secret paths and degrades when expected files are missing.
- `mission_registry.py` - BOT-009 mission creation, status lookup, active/completed listings and search using the existing mission logger/index format plus `missions/Mission-Registry.md` where available.
- `specialist_registry.py` - BOT-010 registry-backed specialist discovery, active/future crew listings, routing recommendations and routing explanations.
- `knowledge_retrieval.py` - BOT-011 local markdown retrieval engine. Classifies knowledge domains, selects focused source documents, loads safe context, reports confidence and refuses secret-file requests.
- `collaboration_engine.py` - BOT-012 simulated multi-specialist collaboration engine. Classifies mission type, selects a specialist team, assigns an owner, generates profile-based viewpoints, consolidates recommendations, captures risks and next actions.
- `knowledge/frameworks/design-review/` - Design review frameworks for UX, product, information architecture, research and USS TJR design principles.
- `mission_executor.py` - BOT-013 synchronous mission execution orchestrator. Creates execution plans, assigns owners and specialists, identifies knowledge sources, updates status, summarizes progress and closes missions.
- `missions/analytics/` - Mission dashboard framework for mission age, completion rate, blocked mission detection, owner workload and mission history reporting.

## Runtime Event Logging

- `logs/runtime-events.jsonl` - Structured JSONL runtime event log written by `runtime_event_logger.py`. Events avoid full request text and secret values.

## Existing Support Modules

- `mission_logger.py` - Existing append-only mission log writer. Preserved for regression compatibility.
- `mission_manager.py` - Earlier mission-history helper retained for compatibility, superseded at runtime by `mission_registry.py`.
- `github_issue_formatter.py` - GitHub issue prompt formatter.
- `github_awareness.py` - GitHub repository awareness helper.
