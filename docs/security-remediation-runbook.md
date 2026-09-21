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

## Agent Diagnostics: Names-Only Environment Checks (mandatory)

Real incident: during a credential-rotation work package, secret **values**
were briefly printed to agent tool output — twice — because a diagnostic
command dumped the full environment instead of just key names. This section
exists so it does not happen a third time.

When any agent (or human, in an agent-observed shell) needs to check what
secrets/env vars are configured — not their values — it must use a
names-only form:

- Allowed: `grep -oE '^[A-Z_0-9]+=' .env` (and the equivalent for any
  `.env*` file) — lists key names only, values stripped before anything is
  ever displayed.
- Allowed: piping an `infisical export --format=dotenv` (or `infisical run
  -- printenv`) straight through `grep -oE '^[A-Z_0-9]+='` in the same
  command, so the unredacted output never lands in a terminal, log, or tool
  result on its own.

Never run, and never let a tool-output-visible command run, any of the
following without a names-only filter already applied in the same pipeline:

- `cat .env` / `cat` on any `.env*` file
- `env` or `printenv` (bare, unfiltered)
- `infisical secrets` or `infisical run -- printenv` / `infisical export`
  without a names-only filter chained on
- Any command that echoes, `curl`s, or otherwise surfaces a decrypted
  secret value to a location an agent's tool-call transcript will capture

If a secret's actual value is genuinely needed (e.g. to hand to a
provider's own rotation flow), that step is a human action outside the
agent's tool-visible surface — the agent states what is needed and who
must do it, and does not attempt to work around this by piping unfiltered
output through a "redaction" step it performs itself after the fact.
