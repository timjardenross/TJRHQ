# Module Map

Overview of runtime modules and responsibilities.

## Runtime Entry

- `app.py` - Slack event entry point. Runtime dispatch order is GitHub issue generation, mission registry, specialist registry, repository awareness, knowledge retrieval, collaboration, then normal Commander response.
- `router.py` - Mission-domain and specialist routing hints for Slack requests.
- `llm.py` - OpenAI client wrapper for normal Commander and issue-generation responses.
- `prompt_loader.py` - Loads local Commander context from command, registry, memory and specialist documents.

## Commander Runtime Capabilities

- `repository_awareness.py` - BOT-008 repository-aware answers using local repository catalogue, source-of-truth and knowledge index documents. Refuses secret paths and degrades when expected files are missing.
- `mission_registry.py` - BOT-009 mission creation, status lookup, active/completed listings and search using the existing mission logger/index format plus `missions/Mission-Registry.md` where available.
- `specialist_registry.py` - BOT-010 registry-backed specialist discovery, active/future crew listings, routing recommendations and routing explanations.
- `knowledge_retrieval.py` - BOT-011 local markdown retrieval engine. Classifies knowledge domains, selects focused source documents, loads safe context, reports confidence and refuses secret-file requests.
- `collaboration_engine.py` - BOT-012 simulated multi-specialist collaboration engine. Classifies mission type, selects a specialist team, assigns an owner, generates profile-based viewpoints, consolidates recommendations, captures risks and next actions.

## Existing Support Modules

- `mission_logger.py` - Existing append-only mission log writer. Preserved for regression compatibility.
- `mission_manager.py` - Earlier mission-history helper retained for compatibility, superseded at runtime by `mission_registry.py`.
- `github_issue_formatter.py` - GitHub issue prompt formatter.
- `github_awareness.py` - GitHub repository awareness helper.
