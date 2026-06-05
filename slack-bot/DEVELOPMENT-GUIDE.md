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

Slack app mentions are handled in this order:

1. GitHub issue generation
2. Mission registry and mission management
3. Specialist registry requests
4. Repository awareness requests
5. Knowledge retrieval requests
6. Existing collaboration path
7. Normal Commander mission response

This order protects existing issue generation while allowing local runtime awareness modules to answer deterministic registry questions without an LLM call.

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

## Sprint 1 Manual Checks

Repository awareness:

- `What folders exist in USSTJROS?`
- `Where should I put a new specialist charter?`
- `What is the source of truth for crew?`
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

### Missing OpenAI Key
Check .env

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
