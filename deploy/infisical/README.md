# Self-hosted Infisical (deploy/infisical)

Recovered 2026-10-04. This directory was never committed: it lived untracked in
a VM-local checkout that was deleted during a disk cleanup on 2026-09-24. The
compose file was rebuilt from the original authoring transcript and checked
against the running containers. No secret values are stored here.

Stack: `db` (postgres:15-alpine), `redis` (redis:7-alpine), `infisical`
(infisical/infisical:latest-postgres). The app joins the external `coolify`
docker network so Coolify's Traefik routes it via labels; it is also published
on 127.0.0.1:8446. `db`/`redis` carry the network aliases `infisical-pg` and
`infisical-redis-svc` (plain `redis` collides with Coolify's own container).
All services use `restart: unless-stopped`.

## Required env var names (put in `.env`, chmod 600, never commit)

| Name | Notes |
|---|---|
| `ENCRYPTION_KEY` | 32 hex chars. MUST match the original, or stored secrets are unreadable. |
| `AUTH_SECRET` | Should match the original so existing sessions/tokens stay valid. |
| `POSTGRES_PASSWORD` | Must match the password already in the existing `infisical-db` volume. |
| `REDIS_PASSWORD` | Any value; redis data is cache/queue only. |
| `SITE_URL` | Public https URL, must match `INFISICAL_DOMAIN`. |
| `INFISICAL_DOMAIN` | Hostname used in the Traefik Host() rule. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS` | Optional mail. |
| `DISABLE_SIGNUP` | Defaults to `true` if unset. Currently `false` in production (open item). |

## Restore notes

- Volumes: `infisical-db`, `infisical-redis`, `infisical-uploads`. With project
  name `infisical` (run from a directory named `infisical`, or `-p infisical`)
  they map to the existing `infisical_infisical-*` volumes.
- To adopt the running stack, run `docker compose -p infisical up -d` with the
  original `.env` values. Compose will only recreate containers whose config
  hash differs, so diff with `docker compose config` first.
- Restoring from a pg_dump onto a fresh volume requires the original
  `ENCRYPTION_KEY` and `AUTH_SECRET`; keep both in an off-VM password manager.
- The container labels of the running stack still point at the deleted path
  `/root/TJRHQ/deploy/infisical`; the next `up` from a new path will relabel them.
