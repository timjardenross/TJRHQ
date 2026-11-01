# Development Guide

## Local Startup

Activate environment:

source .venv/bin/activate

Run Commander:

python app.py

Do not print `.env`, Slack tokens, OpenAI keys or other credentials during startup checks.

## Development Workflow

1. Create issue
2. Create specification
3. Implement
4. Run tests
5. Review logs
6. Commit changes

## Coding Standards

- Small modules
- Clear function names
- Repository-driven design
- Log important actions

## Pre-Commit Checklist

- Application starts
- No secrets committed
- Tests pass
- Documentation updated

## Commander Runtime Dispatch — REMOVED (2026-09-09)

The Slack Commander bot has been removed platform-wide: `app.py` and `commander_bridge.py`
are deleted. `commander_runtime.py` and `router.py` still exist on disk but have zero
importers anywhere in the repo (verified by a full-repo grep for both `import` and
`from ... import` forms, plus a check for dynamic/importlib-based loading) — they are
dead code themselves.

Their removal means the BOT-008/010/011/012/013 modules they dispatched to, and
`runtime_event_logger.py`, are now also confirmed dead:

- **`mission_executor.py` (BOT-013)** — no live callers. Only reference is
  `test_intelligence_loop.py`, a test of its internal helpers.
- **`specialist_registry.py` (BOT-010)** — no live callers; only imported by
  `mission_executor.py`, `collaboration_engine.py`, `router.py`, `commander_runtime.py`,
  all of which are themselves dead.
- **`repository_awareness.py` (BOT-008)** — no live callers; only reference is
  `tests/test_repository_awareness_source_truth.py`.
- **`knowledge_retrieval.py` (BOT-011)** — no live callers. (`prompt_loader.py` has an
  unrelated function that happens to share the name `load_knowledge_retrieval_context`
  but does not import this module.)
- **`collaboration_engine.py` (BOT-012)** — no live callers, no tests.
- **`runtime_event_logger.py`** — no live callers, no tests.

These six modules plus their two dead tests are proposed for deletion; see
`platform-runtime/MODULE-MAP.md` for the disposition list. Confirm with the user before
deleting.

The dispatch order below is historical, describing the removed system for context only:

Slack app mentions were delegated from `app.py` to `commander_runtime.py`, which handled this order:

1. GitHub issue generation
2. Mission executor
3. Mission registry and mission management
4. Specialist registry requests
5. Repository awareness requests
6. Knowledge retrieval requests
7. Existing collaboration path
8. Normal Commander mission response

This order protects existing issue generation while allowing local runtime awareness modules to answer deterministic registry questions without an LLM call.

## Commander Runtime v1.0 — REMOVED (2026-09-09)

Historical description, kept for context; `app.py` no longer exists. The runtime integration layer wrapped the existing BOT modules instead of replacing them. `app.py` was meant to remain a small adapter that extracted Slack text, called `execute_commander_runtime()`, and sent the returned response.

Runtime responsibilities:

- Classify intent
- Select the BOT path
- Load only the context required for that path
- Call the existing BOT module
- Log the mission via `mission_logger.py`
- Emit structured runtime events to `slack-bot/logs/runtime-events.jsonl`
- Return graceful fallback responses when a BOT path fails

## LLM Fallbacks

`llm.py` does not construct an OpenAI client at import time. GitHub issue generation and default Commander responses use safe LLM calls and fall back to deterministic responses when the selected LLM provider is unavailable.

Commander is local-first:

1. `LLM_PROVIDER=auto` tries Ollama first.
2. If Ollama is unavailable and OpenAI credentials exist, OpenAI is used as an optional fallback.
3. If no provider succeeds, Commander returns a deterministic fallback.

Local setup:

```bash
ollama serve
ollama pull qwen3:8b
```

Environment:

```bash
LLM_PROVIDER=auto
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
OLLAMA_COMMANDER_MODEL=qwen3:8b
OLLAMA_ENGINEER_MODEL=deepseek-coder:6.7b
OLLAMA_REASONING_MODEL=deepseek-r1:14b
OLLAMA_FAST_MODEL=gemma3
OPENAI_API_KEY=
OPENAI_ADMIN_KEY=
```

Specialist model routing:

- Chief Engineer and technical/repository analysis use `OLLAMA_ENGINEER_MODEL`.
- Research Officer, discovery and trade-off analysis use `OLLAMA_REASONING_MODEL`.
- Executive Officer (XO), Knowledge Officer, Medical Officer and general Commander activity use `OLLAMA_COMMANDER_MODEL`.
- If the selected Ollama model is unavailable, Commander falls back to Commander model, then fast model, then deterministic fallback.
- `OLLAMA_EMBEDDING_MODEL` is reserved for indexing/search and is never used for conversational responses.

Fallback checks:

- `Create a GitHub issue to add mission reporting`
- `Hello Commander`

Both should return useful responses even without `OPENAI_API_KEY`.

## Runtime Event Logger

`runtime_event_logger.py` owns CRT-style JSONL event emission. Event logging must never raise into the request path and must redact secret values before writing metadata or messages.

## Mission Executor Checks

BOT-013 is a synchronous mission execution planner. It does not run background workers, execute shell commands, perform autonomous code/file changes, or continue work later.

Manual checks:

- `Create a mission to redesign the USSTJR-Website UI.`
- `Start a mission for Voice Core planning.`
- `Assign Research Officer and Medical Officer to review Medical Bay.`
- `Update mission <mission id> as blocked because credentials are pending.`
- `Show progress on mission <mission id>.`
- `Close mission <mission id> and summarise the outcome.`

## Mission Dashboard Checks

Mission analytics are deterministic and use `Missions/Mission-Index.md` plus mission record files.

Manual checks:

- `Show mission health`
- `Show blocked missions`
- `Show overdue missions`
- `Show mission metrics`

## Knowledge Retrieval Checks

BOT-011 retrieves focused local markdown context and returns source paths, confidence, gaps and next actions. It must refuse `.env`, `.venv/`, API keys, tokens and credential requests.

Manual checks:

- `What do the Captain's Directives say about build small?`
- `What is the process for closing a mission?`
- `Where do we track capabilities?`
- `What fields should a specialist profile include?`
- `Explain the runtime module design.`
- `What is the current Supabase schema?`
- `Read .env`

## Collaboration Checks

BOT-012 uses simulated specialist reasoning from local specialist profiles. It is not a multi-agent implementation and does not call the LLM for each specialist.

Manual checks:

- `Review USS TJR architecture`
- `Review USS TJR roadmap`
- `Review chronic pain coaching framework`
- `Review repository structure`
- `Review Voice Core proposal`
- `Review governance framework`
- `Major strategic decision`
- `Review Medical Bay UX`

## Sprint 1 Manual Checks

Repository awareness:

- `What folders exist in USSTJROS?`
- `Where should I put a new specialist charter?`
- `What is the source of truth for crew?`
- `What is the source of truth for knowledge?`
- `Where is mission ownership defined?`
- `What should Codex read before implementing BOT-010?`
- `Review the repository structure`

Mission registry:

- `Create a mission for Repository Awareness`
- `Show active missions`
- `Show completed missions`
- `Show status of <mission id>`
- `Find repository missions`

Specialist registry:

- `What specialists exist?`
- `What future specialists exist?`
- `Who should review architecture?`
- `Who should review chronic pain research?`
- `Why did you select the Chief Engineer?`

## Troubleshooting

### LLM Provider Unavailable
Check that Ollama is running with `ollama serve` and that the selected model has been pulled. OpenAI keys are optional and should only be configured when paid fallback is intended.

### Slack Not Responding
Verify bot token and socket mode.

### Specialist Not Found
Check Crew Registry and specialist profile.

## Future Modules

All new modules require:
- Specification
- Acceptance criteria
- Test cases
- Documentation
