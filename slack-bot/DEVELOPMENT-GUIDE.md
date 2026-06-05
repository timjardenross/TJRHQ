# Development Guide

## Local Startup

Activate environment:

source .venv/bin/activate

Run Commander:

python app.py

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
