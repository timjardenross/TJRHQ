# TJRHQ Command Centre — Read-only Architecture & Security Audit

Date: 2026-11-06 (AEDT) · Host: single KVM VM, Ubuntu 24.04.5 LTS (kernel 6.8.0-147) · Repo HEAD at audit: `d6dda199f` (PR #592, branch `main`)
Method: read-only inspection of the live VM (ss, systemctl, ufw/iptables, Caddyfile, repo source, local HTTP probes that print status codes/booleans only). No secret values were read or printed. `.env`, `caddy.env` and auth files were not opened.

Legend: **VERIFIED** = observed on the VM · **INFERRED** = follows from verified facts but not tested directly · **UNKNOWN** = needs access not available here.

Disclosure: running `pm2 list` auto-spawned an empty PM2 daemon (no managed processes). It is a minor side effect against the read-only rule; `pm2 kill` removes it. Nothing else was changed.

---

## A. Executive summary

- The VM is a single point of everything: 14 app services, a Node backend, a Next.js portal, Python schedulers, Telegram bots, Docker apps (Infisical, Uptime Kuma, changedetection) and Ollama, **all running as root** (VERIFIED for the 11 app services checked).
- Edge is reasonably tight: host firewall is deny-by-default with only 22/80/443 open (VERIFIED); Caddy is the only reverse proxy; only `/api/v1/*`, `/health`, and a few path-prefixed services are proxied to backends (VERIFIED).
- **Most important finding:** the Express backend exposes `GET /api/config`, which returns the backend API key **without authentication** (VERIFIED: local probe returned HTTP 200 with a non-empty `apiKey`). It is *not* reachable through Caddy (`/api/config` is not routed to the backend; it hits the portal and redirects to `/login`), and port 5000 is blocked by the firewall (INFERRED, not tested from outside). So it is a latent, not currently exploitable-from-internet, defect. It nullifies the API key as a security control for anything that can reach port 5000.
- The backend also accepts the key in a **query string**, compares it non-constant-time, and uses a **single shared static key** with no per-caller identity or roles.
- Several services listen on `0.0.0.0` (5000, 3200, 4317, 6006, 8765, 8766, 8893) and rely solely on the host firewall.
- Reliability is decent day to day (all checked services `NRestarts=0`, nightly encrypted off-box backup succeeding), but there is no staging, auto-deploy goes straight from `main` to production every 5 minutes, and restore has not been tested (UNKNOWN).
- Vercel configuration, live Supabase RLS state and Infisical contents could not be inspected from here (UNKNOWN).

---

## B. Verified architecture (text diagram)

```mermaid
flowchart LR
  Browser -->|HTTPS| Vercel[Vercel: LCARS Portal (per Caddyfile comments; config UNKNOWN)]
  Browser -->|HTTPS 443| Caddy
  Vercel -->|HTTPS sslip.io host, X-Api-Key / X-*-Secret| Caddy
  subgraph VM[Single VM - Ubuntu 24.04, ufw: 22/80/443 only]
    Caddy[Caddy :80/:443] -->|/api/v1/*, /health| CC[Command Centre Express :5000]
    Caddy -->|/context-service| CTX[context-service :5001 127.0.0.1]
    Caddy -->|/self-improvement| SI[dashboard :8892 127.0.0.1]
    Caddy -->|/tts| TTS[chatterbox :8893]
    Caddy -->|/changedetection, /uptime| DK[Docker apps 127.0.0.1:5050,:3001]
    Caddy -->|everything else| LP[lcars-portal Next.js :3200]
    Sched[intelligence-scheduler / human-systems-scheduler / command-bus] --> Supa
    Bots[tg-xo / tg-capacitybot / tg-resiliencebot] --> TG[Telegram API]
    MR[model-router :8891] --> Ollama[:11434 127.0.0.1] 
    Infisical[Infisical docker 127.0.0.1:8446] --> Wrapper[run-with-infisical-bot.sh] --> Sched
  end
  CC --> Supa[(Supabase project cjvrpjwewsrumnbdydgg)]
  LP --> Supa
  Browser --> Supa
```

Trust boundaries: Internet → Caddy (TLS) · Vercel → VM (shared-secret headers) · Browser → Supabase (anon key + RLS) · VM services → Supabase (service-role, server side) · Telegram → bots (allowlist) · Infisical → processes (env injection at start).

---

## C. Service inventory, bind addresses, exposure

Firewall (VERIFIED): `ufw` active, default deny incoming; allow 22, 80, 443 (any); 8081 and 8444 only from 10.0.0.0/8. iptables INPUT policy DROP. Docker-published ports are bound to 127.0.0.1.

| Port | Bind | Service (manager) | User | Externally reachable |
|---|---|---|---|---|
| 80, 443 | `*` | Caddy (systemd) | caddy | **Yes** (intended) |
| 22 | 0.0.0.0, `[::]` | sshd (systemd) | root | **Yes** (fail2ban active; sshd config not reviewed) |
| 5000 | `*` | command-centre (Node, systemd) | root | No (firewall); via Caddy only `/api/v1/*`, `/health` |
| 3200 | `*` | lcars-portal (Next.js, systemd) | root | Via Caddy catch-all (login required); direct blocked by firewall |
| 4317, 6006 | 0.0.0.0 | phoenix tracing (systemd) | root | No (firewall) |
| 8765, 8766 | 0.0.0.0 | watchlist webhook receivers (systemd) | root | No (firewall) |
| 8893 | 0.0.0.0 | chatterbox-tts (systemd) | root | Via Caddy `/tts/*` (own header auth) |
| 5001 | 127.0.0.1 | context-service (gunicorn) | root | Via Caddy `/context-service/*` |
| 5052 | 127.0.0.1 | mint-server | root | No |
| 8891 | 127.0.0.1 | model-router | root | No |
| 8892 | 127.0.0.1 | self-improvement-dashboard | root | Via Caddy `/self-improvement/*` |
| 5050, 3001 | 127.0.0.1 | changedetection, Uptime Kuma (Docker) | container | Via Caddy `/changedetection`, `/uptime` (native logins) |
| 8446 | 127.0.0.1 | Infisical (Docker) | container | No |
| 11434 | 127.0.0.1 | Ollama | – | No |
| 7700 | 127.0.0.1, `::1` | Meilisearch | – | No |
| 2019 | 127.0.0.1 | Caddy admin API | caddy | No |

Other running units: tg-xo, tg-capacitybot, tg-resiliencebot, intelligence-scheduler, human-systems-scheduler, command-bus, number-one-exporter, plus ~30 systemd timers (auto-deploy, backup, verification-engine, deadmans-switch, etc.). Reverse proxy: Caddy only (nginx, cloudflared, tailscaled, traefik, haproxy, apache2 are inactive). PM2 has no managed processes. Failed unit: `systemd-networkd-wait-online` (cosmetic).

---

## D. Vercel-to-VM communication

- VERIFIED (Caddyfile comments + config): Caddy serves a Let's Encrypt cert on `109-123-227-196.sslip.io` "for Vercel's server-side fetches". Proxied paths: `/api/v1/*`, `/health` → :5000; `/context-service/*`, `/self-improvement/*`, `/tts/*`. Auth is by caller-supplied headers (`X-Api-Key`, `X-Context-Service-Secret`, `X-Self-Improvement-Secret`, `X-TTS-Secret`). Caddy no longer injects keys.
- VERIFIED: bare-IP site uses `tls internal` (self-signed); sslip.io host uses a public cert. Transport is public HTTPS, no private tunnel (no Tailscale/Cloudflare Tunnel).
- VERIFIED (code): portal server routes read `COMMAND_CENTRE_API_URL`, `COMMAND_CENTRE_API_SECRET`, `CONTEXT_SERVICE_URL` (e.g. `lcars-portal/src/lib/contextService.ts`, `src/app/api/advisory/route.ts`).
- Probe (VERIFIED): `GET /api/v1/health` without key through Caddy → 401; `GET /health` → 200; `GET /api/config` via Caddy → 307 `/login` (served by portal, not backend).
- **UNKNOWN:** the actual value of `COMMAND_CENTRE_API_URL` on Vercel, which routes call the VM vs Supabase directly, and whether a Vercel production deployment is currently live. The VM also runs its own copy of the portal on :3200, which is a duplicate surface.
- Portal auth: Next.js `middleware.ts` uses Supabase SSR sessions, an exact-match public allowlist, a bot-secret allowlist (single route `/api/google-tasks/sync`, constant-time compare) and bearer routes for mobile/health bridge.

---

## E. Supabase security findings

- Project id (non-secret): `cjvrpjwewsrumnbdydgg`. Browser CSP `connect-src` allows only this project.
- VERIFIED (repo): `core/infrastructure/supabase/migrations` has 77 files creating tables, 64 with `ENABLE ROW LEVEL SECURITY`, **56 files containing `USING (true)`** policies, 6 with `SECURITY DEFINER` functions.
- INFERRED: `USING (true)` is only safe when scoped `TO service_role`; I did not classify each policy. Several earlier fixes (public-writable advisory sessions, anon-key exposure) show this class of bug has occurred in this project.
- VERIFIED: no `NEXT_PUBLIC_*` variable names containing SERVICE/SECRET/ROLE found in the portal source.
- **UNKNOWN (no DB access; Supabase MCP not authenticated in this session):** live RLS state per table, actual policy roles, grants to `anon`/`authenticated`, RPC/function exposure, Edge Functions, and migration-vs-live drift.

---

## F. Authentication and agent-execution findings

- Backend (Express `core/command-centre/backend/app.js`): single global middleware (lines 80–93) runs before all `/api/v1/*` routes (routes mounted lines 128–146), so every route there needs the shared key. Exempt: `/health` and `/api/config` (line 81). Fails closed (503) in production if the key is unset.
- Authorization: **no roles**. The one key grants access to missions, console, capture, governance, notifications, etc. Per-endpoint privilege checks were not reviewed in depth (UNKNOWN). Files using `child_process`: `api/notifications.js`, `api/intelligence.js`, `api/captains-log.js`, `api/intel-governance.js`, `api/advisory.js`, `api/health.js`, and three connectors. Whether any execute attacker-influenced input is UNKNOWN.
- Bots: Telegram bots run as root; XO is documented as action-capable with plan-then-approve and a Captain-only allowlist (from project notes; not re-verified here).
- Secrets: Infisical injects them at process start through `run-with-infisical-bot.sh`; the wrapper refuses to start without secrets. Only whether a secret is configured was checked, never values.
- Prompt injection: scheduler/agents ingest untrusted web/RSS content (intelligence ingestion). Whether any path lets ingested text trigger privileged actions is UNKNOWN; no tool-execution path from ingestion was found in the code I read.
- Logging: backend logs method, path, status (not query string) — good. Caddy logs full request URI at INFO to stderr, so a key sent as `?api_key=` would land in the journal.

---

## G. Security findings

| ID | Severity | Evidence | Impact | Recommended fix |
|---|---|---|---|---|
| S1 | **High** (latent; Medium effective) | `core/command-centre/backend/app.js:81` exempts `/api/config`; `:105-108` returns `{apiKey}`. VERIFIED local probe: 200, key non-empty. Not routed by Caddy; port 5000 firewalled (INFERRED) | Anything that can reach :5000 (local process, SSRF, container, firewall change) obtains the master key and full API access | Delete the endpoint and its callers; serve key to no one. Bind :5000 to 127.0.0.1 |
| S2 | Medium | `app.js:88` accepts `req.query.api_key`; Caddy logs full URI (Caddyfile `log` block) | Key leaks into logs, proxies, browser history | Accept header only |
| S3 | Medium | `app.js:89` uses `!==`; single shared key; no roles; no rate limiting seen | Timing and brute-force exposure; no attribution; one leaked key = total access | `crypto.timingSafeEqual`; per-client keys/scopes; rate limit; Caddy `rate_limit` |
| S4 | Medium | Listeners on `0.0.0.0`: 5000, 3200, 4317, 6006, 8765, 8766, 8893 (VERIFIED `ss`) | Only the firewall prevents exposure; one ufw change or Docker iptables bypass exposes Phoenix UI/webhooks | Bind to 127.0.0.1 where Caddy fronts them |
| S5 | Medium | 11 of 11 checked app services run as `root` (VERIFIED `ps`) | RCE in any service (bot, portal, ingestion) = full host takeover | Dedicated unprivileged users, `NoNewPrivileges`, `ProtectSystem` per unit |
| S6 | Medium | 56 migration files with `USING (true)` (VERIFIED count); live state UNKNOWN | Possible over-permissive RLS | Run an RLS audit against the live DB; restrict to `service_role` |
| S7 | Low | CSP allows `unsafe-inline`/`unsafe-eval` (Caddyfile); bare-IP site uses self-signed cert | Weaker XSS defence; users trained to click through warnings | Nonce-based CSP; use only the real-cert host |
| S8 | Low | CORS default allows localhost origins with `credentials: true` (`app.js:51-59`); `CORS_ORIGIN` setting UNKNOWN | Misconfiguration risk | Explicit production origin list |
| S9 | Low | Public GitHub repository with operational docs | Information disclosure; publishing findings before fixes widens exposure | Keep security reports in a private location until fixed |
| S10 | Info | SSH open to the internet; fail2ban active; sshd config not reviewed | Brute-force surface | Confirm key-only auth, or restrict by IP |

---

## H. Reliability and deployment

- VERIFIED: `auto-deploy.timer` every 5 min (2 min after boot), runs `deploy/auto-deploy.sh` as user `deploy` with permission-repair pre-steps. During this audit session, PRs #587→#592 were deployed this way, and at least one deploy restarted `intelligence-scheduler` without notice.
- VERIFIED: deployed branch is `main`, HEAD `d6dda199f`. No staging; merge to `main` = production on the VM within minutes. Rollback procedure: UNKNOWN (git revert is the only mechanism seen).
- VERIFIED: all 14 app services `ActiveState=active`, `NRestarts=0`. Only failed unit is `systemd-networkd-wait-online`.
- VERIFIED: nightly `starship-backup` (restic to Google Drive, encrypted) succeeded 2026-11-06 02:42; next 2026-11-07 02:40. Restore test: UNKNOWN.
- Monitoring present: Uptime Kuma, deadmans-switch timer, verification-engine, heartbeats in Supabase (with a 20-min healthy-write throttle, so latest-heartbeat views can look ~30 min stale).
- Config drift: Infisical secrets are inconsistent with the wrapper's expectations at least once this session (a flag saved in the UI never reached the service); a systemd drop-in was used as a stopgap, then removed.
- Dependencies / versions: not audited (UNKNOWN). Docker images use `latest` tags (`changedetection.io:latest`, `infisical:latest-postgres`), which makes deploys non-reproducible.

---

## I. Top five fixes (severity × effort)

1. **Remove `/api/config` and the `api_key` query parameter** (S1, S2): a few lines in `app.js`; first check whether any frontend still calls it.
2. **Bind 5000/3200/4317/6006/8765/8766/8893 to 127.0.0.1** (S4): config-only, low risk, removes dependence on the firewall alone.
3. **Run services as non-root users with systemd hardening** (S5): medium effort, largest blast-radius reduction.
4. **Live RLS and grants audit on Supabase, fix `USING (true)` policies** (S6): needs DB access; highest data-exposure risk that is currently UNKNOWN.
5. **Per-client API keys with constant-time compare, rate limiting and request attribution** (S3), plus a staging/rollback step for auto-deploy.

---

## J. Unknowns requiring additional access

- Vercel project settings: env vars, which routes call the VM, deployment status (needs Vercel access).
- Supabase live schema: RLS per table, policies, grants, RPCs, Edge Functions, migration drift (needs authenticated Supabase access).
- External reachability test of ports 5000/3200/6006/etc. from outside the VM (firewall rules say blocked; not tested from outside).
- Per-endpoint authorization and command-execution paths in the backend `api/*.js` files.
- Telegram bot allowlist enforcement and approval gates (re-verify in code).
- Infisical project contents and machine-identity permissions.
- sshd configuration, OS patch level, dependency vulnerabilities, restore test of backups.
