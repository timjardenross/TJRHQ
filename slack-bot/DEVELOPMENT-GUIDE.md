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

## Commander Runtime Dispatch

Slack app mentions are delegated from `app.py` to `commander_runtime.py`, which handles this order:

1. GitHub issue generation
2. Mission executor
3. Mission registry and mission management
4. Specialist registry requests
5. Repository awareness requests
6. Knowledge retrieval requests
7. Existing collaboration path
8. Normal Commander mission response

This order protects existing issue generation while allowing local runtime awareness modules to answer deterministic registry questions without an LLM call.

## Commander Runtime v1.0

The runtime integration layer wraps the existing BOT modules instead of replacing them. `app.py` should remain a small adapter that extracts Slack text, calls `execute_commander_runtime()`, and sends the returned response.

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
- Chief of Staff, Knowledge Officer, Medical Officer and general Commander activity use `OLLAMA_COMMANDER_MODEL`.
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
