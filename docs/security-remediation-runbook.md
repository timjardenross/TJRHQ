# Security Remediation Runbook

## Scope

This runbook covers the runtime security controls for the command-centre backend and related local configuration files.

## Environment Files

- Keep all `.env` files owner-readable only (`600`).
- Do not commit non-example `.env` files.
- Repository `.env` locations currently discovered:
  - `/.env`
  - `/core/command-centre/.env`
  - `/slack-bot/.env`
  - `/slack-bot/.env.commander`
  - `/slack-bot/.env.engineering`

## File Permission Requirements

- Validate permissions after any secret update.
- Recommended command:

```bash
chmod 600 .env core/command-centre/.env slack-bot/.env slack-bot/.env.commander slack-bot/.env.engineering
```

- Example verification:

```bash
stat -f '%Sp %N' .env core/command-centre/.env slack-bot/.env slack-bot/.env.commander slack-bot/.env.engineering
```

## Backend API Key Requirements

- `BACKEND_API_KEY` is mandatory.
- Backend startup fails fast if `BACKEND_API_KEY` is missing.
- All `/api` and `/api/v1/*` routes require the `X-Api-Key` header or `api_key` query parameter.
- The `/health` endpoint remains public for process liveness checks.
- Do not expose the backend through ngrok or any public tunnel unless the key is set and verified.

## Startup Validation Expectations

- A backend start without `BACKEND_API_KEY` should exit with a clear fatal message.
- A valid startup should log normally and serve authenticated routes.
- Validate both cases locally after any auth-related change:
  - Missing key: startup must fail.
  - Present key: authenticated requests succeed; unauthenticated requests return `401`.

## Runtime Database Governance

- Runtime-generated SQLite databases must not be tracked in git.
- The root `missions.db` is a runtime artifact and is ignored.
- Any duplicate runtime database copies in `archive/quarantine/finder-duplicates/` are ignored and should remain local only.
- Do not delete local database files during remediation unless explicitly requested.

## ngrok Exposure Considerations

- Public tunnels increase blast radius immediately if authentication is misconfigured.
- Treat ngrok as production exposure:
  - confirm `BACKEND_API_KEY` is present,
  - confirm startup passes fail-fast validation,
  - confirm unauthenticated requests are denied before opening a tunnel.

## Operational Checklist

1. Set permissions on all `.env` files to `600`.
2. Confirm `.env` files are not committed.
3. Confirm `BACKEND_API_KEY` is set in the active environment.
4. Start the backend locally.
5. Verify unauthenticated requests are rejected.
6. Verify authenticated requests succeed.
7. Confirm runtime database files are ignored by git.
