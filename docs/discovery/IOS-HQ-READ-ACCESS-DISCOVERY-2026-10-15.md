# TJRHQ Discovery Report: iOS App Read Access to HQ Data (Bearer Auth)

Type: read-only discovery. No code changed, nothing deployed, nothing sent.
Pinned to: TJRHQ `main` at `f9ec42735ad967939b2d0c66b6b88e429ba58fa3`
(merge of PR #397, committed 2026-10-15 14:53 +1100). `origin/main` was re-fetched
and is the same SHA. All file references below are at that SHA.
Filed as: docs-only DRAFT PR. Do not merge it (see Q12: any merge to main restarts bots).
No tokens, secrets or message content are in this report.

Legend: VERIFIED = read in code at the SHA above. LIVE-READ = read-only catalogue
query against the live Supabase project (policy metadata only, no row data).
NOT VERIFIED = could not confirm.

---------------------------------------------------------------------------

## 1. Verdict: GO WITH CHANGES

Doable, size M for a useful subset, L for full Captain's Chair parity. The
hypothesis in section 4 of the brief is mostly right. Four changes to it:

1. Captain's Chair has no single API. The page assembles itself in the browser from
   about 15 routes (`lib/captainsChairData.ts`) and derives posture in client-side
   TypeScript (`lib/commandState.ts`, `lib/captainsChairSynthesis.ts`). Bearer-enabling
   the existing routes gives the app raw ingredients, not Captain's Chair. A phone view
   needs a purpose-built snapshot route (your fallback), built on those same pure
   functions.
2. The Captain-id check is the ONLY real gate. Every read policy on the candidate
   tables is `authenticated USING (true)` (LIVE-READ, Q7). The database cannot tell
   the Captain from any other signed-in user. The live project has 3 auth users.
   Today's cookie flow has the same weakness ("any logged-in user is the Captain",
   `lib/supabase-server.ts:28-40`), so the bearer path must be stricter than the
   cookie path, not equal to it.
3. `lib/supabase-server.ts` starts with `'use server'` (line 1). Every export in it
   must be an async function. Any new helper there must be async.
4. Several candidate routes are unsuitable (Q16). The v1 allowlist is small.

---------------------------------------------------------------------------

## 2. Answers 1 to 16

### AUTH

**1. Can Edge middleware verify a Supabase JWT and compare to a Captain id? VERIFIED**
Yes. `middleware.ts:61-82` already runs `@supabase/ssr` `createServerClient` and
`supabase.auth.getUser()` in the Edge runtime on every request. That is a network call
to Supabase Auth, which is server-side validation (revocation-aware), not local JWT
signature checking. `getUser(token)` is the same call with an explicit token, so no new
Edge capability is needed. The only Edge limit hit so far was Node `crypto`
(`middleware.ts:21-38` documents that bug). Bearer verification needs no Node built-ins.
The ping route (`api/integrations/health-bridge/ping/route.ts:12-60`) does exactly this:
regex-parses `Bearer`, `createClient(... persistSession:false)`, `auth.getUser(token)`,
then `user.id === HEALTH_BRIDGE_CAPTAIN_USER_ID`. It is a Node route only because it is
an ordinary App Router handler. Nothing about it needs Node. Middleware exempts that
exact path (`middleware.ts:19,47-49`) so the cookie flow does not redirect it, and the
handler does all verification itself.
Cost of middleware verification: one extra Supabase Auth round trip per request, and
two if the route also verifies (recommended, Section 4).
`HEALTH_BRIDGE_CAPTAIN_USER_ID` is not in `.env.example`. NOT VERIFIED that it is set
in production.

**2. How is `createSupabaseServerClient` used across the 77 files? VERIFIED**
Counts at this SHA: 83 files reference `createSupabaseServerClient` (brief said 77),
135 reference `requireSession` (brief said about 134), 132 `route.ts` files.
- `requireSession()` returns the Supabase `session` object, or null (`supabase-server.ts:34-40`).
- No caller reads `access_token`. Callers read `session.user.id` (shopping-list views)
  or `session.user.email` (`missions/[id]`, `knowledge-library/.../decide`,
  `content-workbench/[id]/qa|draft`) to stamp authorship. Every candidate route only
  tests truthiness.
- So a bearer-aware `requireSession` is safe if it returns an object with a `user`
  (id and email). It must also work with no cookie context at all. Safest: leave
  `requireSession` untouched and add a separate `requireCaptainRead()` used only by
  allowlisted routes. That avoids silently granting bearer access to the ~120
  mutating routes that call `requireSession`.

**3. Does RLS apply as the user with a bearer-built client? Service role vs user client? VERIFIED (code), RLS behaviour not executed**
A client built with `createClient(url, anonKey, { global: { headers: { Authorization: 'Bearer <jwt>' } } })`
makes PostgREST run as the `authenticated` role with `auth.uid()` set. This is standard
Supabase behaviour. I did not execute it. None of the candidate routes uses a
service-role client (grep over `emergency-alerts`, `briefs`, `captains-daily-brief`,
`operating-picture`, `agent-status*`, `home`, `health-osint`, `captain-brief` finds none).
All use the user client. Service role appears only in `lib/ai-actions.ts` and
`lib/ai-context.ts` and about 18 mutating routes (content-workbench, comms, learning
etc.), none on the allowlist. Because every read policy is `USING (true)` for
`authenticated`, RLS adds no Captain-specific protection on these tables. The Captain
check is the only gate.

**4. Routes with no `requireSession` of their own (middleware-only)? VERIFIED**
Five `route.ts` files lack the string `requireSession`:
`ai/chat`, `perspectives`, `xo`, `build-request/[id]/approve-action` and the health-bridge ping.
The first four check `supabase.auth.getSession()` themselves (e.g. `ai/chat:180`,
`perspectives:33,75`, `xo:112`, `approve-action:33`). Caution: `getSession()` on the
server reads the cookie without re-validating the token. They are protected by
middleware's `getUser()` plus that check. Ping is bearer-only. None is on the proposed
allowlist. Non-API pages are middleware-only by design.
Subtle risk if a bearer allowlist is added: a bearer request that passes middleware
but reaches a route that only checks `getSession()` would fail closed (no cookie, so no
session). That is safe. The danger is only a route with NO check at all, and there are none under `/api`.

### DATA

**5 and 6. Per-route detail (shape, size, source, side effects, dependencies). VERIFIED (code). Payload sizes and latency NOT MEASURED**
I did not read production rows, so "typical" size and latency are NOT VERIFIED.
Maximum row bounds come from the code.

| Route | Source | Bound | GET side effects | Server-only dependency | Phone fit |
|---|---|---|---|---|---|
| `/api/emergency-alerts` | table `alerts` (user client) | 500 rows, includes `raw_text`, lat/long; filters via query string | none | none | Good with changes (trim `raw_text`, limit) |
| `/api/captains-daily-brief` | `captains_daily_briefs` | 20 rows incl. `brief_text`, `health_snapshot` | none | none | Good, needs sensitivity decision (Q10) |
| `/api/briefs` | `intelligence_briefs` | 100 rows, 16 columns incl. several jsonb | none | none | Heavy for a phone; prefer "latest 1" |
| `/api/briefs/[id]` | briefs + `intelligence_events` + `audit_events` | up to 20 signals + 50 audit rows | none | none | OK later; includes audit trail (Q10) |
| `/api/agent-status-workbench/overview` | 6 queries (heartbeats, quality views, source health up to 1000 rows) | many | none | none | Right source for "HQ status" but heavy; use `captainSummary` only |
| `/api/agent-status` | `domain_heartbeats_latest` via `lib/agentStatusJobs` | about 40 jobs | none | none | Too raw |
| `/api/home/needs-attention` | signals, interrupts, source health | 5+2+3 rows | none | none | Light, good, but returns source `error_message` text |
| `/api/operating-picture` | missions, decisions, signals, transitions | up to 200 missions | none (comment says read-only) | reads `.id-counters.json` from `REPO_ROOT` or `cwd/..` | Unsuitable (Q16) |
| `/api/captain-brief` | HTTP call to context service | 15 s timeout | none | needs `CONTEXT_SERVICE_URL` and secret | Unsuitable (Q16) |
| `/api/briefs/domains` | same context service | 15 s timeout | none | same | Unsuitable |
| `/api/health-osint/*` | `health_signals` etc. | up to 100 rows (`today`) | none | `intelligence-summary` reads a repo config file | Web-shaped, raw OSINT, exclude |
| `/api/emergency-alerts/silences` | `alert_silences` | list | **POST on same path mutates** | none | Exclude (mixed-method path) |
| `/api/emergency-alerts/sources` | `alert_sources SELECT *` | all sources | none | none | Exclude from v1 (returns feed URLs, notes) |

Caching: handlers do not set `Cache-Control`. They call `cookies()`, so Next treats them
as dynamic. A new bearer path must set `Cache-Control: private, no-store` explicitly,
as the ping route does.

**Captain's Chair (Q6): VERIFIED.** There is no `/api/captains-chair`.
`app/captains-chair-workbench/page.tsx:36-54` calls hooks in `lib/captainsChairData.ts`
that fetch: `/api/human-systems/context`, `/api/intelligence-workbench/credibility` and
`/threat-assessment`, `/api/emergency-alerts` and `/sources`,
`/api/agent-status-workbench/overview`, `/api/captain-brief`, `/api/calendar/today` and
`/upcoming`, `/api/content-workbench`, `/api/human-systems?domain=recovery`,
`/api/self-improvement/evolution-summary`, `/api/number-one-brief`, `/api/remember`,
plus the alerts engine (`lib/alerts.ts`, which fans out to 6 sources). Posture and
"Needs You" are computed client-side by pure functions. The code says "so LifeOS can
render the identical list", so reusing them server-side was anticipated.

**HQ status (Q6):** `/api/agent-status-workbench/overview`, specifically its
`captainSummary` field (built by `buildCaptainChairSummary` in `lib/hqStatusInterpreter.ts`).
That is what Captain's Chair itself uses (`captainsChairData.ts:246`). Not
`/api/agent-status` (raw job list).

**7. RLS policies. LIVE-READ (read-only `pg_policies` query on the production project) plus VERIFIED (migrations)**

| Table | Live SELECT policy |
|---|---|
| `alerts`, `alert_sources`, `alert_silences` | role `public` (includes **anon**), `USING (true)` |
| `domain_heartbeats` | role `public`, `USING (true)` |
| `intelligence_source_health` | `anon_read`, role `public`, `USING (true)` |
| `captains_daily_briefs` | `authenticated`, `true` |
| `intelligence_briefs`, `intelligence_events`, `intelligence_source_registry` | `auth_read`, `authenticated`, `true` (plus `xo_bot`) |
| `health_signals`, `health_source_*` | role `public` with `auth.role() = 'authenticated'` |
| `missions`, `mission_state_transitions`, `command_memory_records`, `audit_events` | `authenticated`, `true` |

Findings:
- The Captain does have SELECT everywhere needed. So does **any** authenticated user.
- `alerts`, `alert_sources`, `alert_silences`, `domain_heartbeats` and
  `intelligence_source_health` are readable by anyone holding the public anon key,
  with no login. Emergency alerts are public information, but this is a real,
  pre-existing exposure. Not caused by this work; flag only.
- The repo migrations and live DB disagree: `intelligence_briefs` and
  `intelligence_events` `auth_read` exists live (migration 0109 says it does) but I
  found no migration in the repo creating it, and `0123` says "implicit deny". The
  repo is not a reliable record of live RLS. Re-check live state before any change.

**8. Brief text format. VERIFIED**
`captains_daily_briefs.brief_text` is Telegram HTML (`<b>`, `<i>`, entities
`&amp; &lt; &gt;`), returned raw by `/api/captains-daily-brief`. The app must strip tags
FIRST, then decode entities (decoding first would turn an escaped `&lt;NRP&gt;` into a
tag that then gets stripped). Reference implementation: `lib/briefText.ts`
(`parseBriefText`, `decodeBriefEntities`). Render as plain text only, never in a
WebView or attributed HTML. Alert fields (`headline`, `description`, `raw_text`) come
from external feeds and are untrusted text. Format of `intelligence_briefs` text
fields (markdown or plain): NOT VERIFIED. Recommendation: the snapshot route
normalises briefs to plain-text lines server-side so the app does not parse HTML.

### SECURITY AND PRIVACY

**9. Threat model. Partly VERIFIED, session settings NOT VERIFIED**
- Leaked access token: valid until expiry. Supabase default is 1 hour. The project's
  JWT expiry and refresh-rotation settings are NOT VERIFIED. A leaked token gives the
  holder read of everything on the allowlist until expiry, and `getUser()` (server
  validated) also rejects it once the session is revoked (expected for current GoTrue,
  NOT VERIFIED here).
- Lost phone: Keychain-stored session. Mitigation is server side: sign out all
  sessions for the Captain (Supabase Auth) and remove the Captain id env var.
- Token reuse: tokens are not bound to a device or to this API. The same token also
  works against the Supabase REST API directly with the anon key and the RLS above.
  Bearer read on HQ adds no capability the token did not already have against
  Supabase, except via HQ's server-side assembled routes.
- Rate limiting: only `lib/rateLimit.ts`, an in-memory per-instance limiter, applied to
  `captain-brief` and `briefs/domains` only. It states it is "not a security
  boundary". No limiter on any other candidate route. For a bearer allowlist, add one
  per Captain id (still in-memory is acceptable for one user), and consider a Vercel
  firewall rule (Q11).
- Logging: candidate routes `console.error` the caught error object only
  (`captains-daily-brief:37`, `briefs:52`, `briefs/[id]:76`). No route logs the
  Authorization header, token or brief content. Middleware logs nothing. Ping
  deliberately swallows errors. Note: several routes return `errorDetail(err)`
  (raw Postgres message and hint) to the client in 500 responses
  (`emergency-alerts:87`, `agent-status:38`, `operating-picture:158`). That is
  schema leakage to anything holding a token, so a snapshot route should not do that.
  Platform request logs (Vercel or Caddy) would record method, path and status; I did
  not verify whether Caddy logs headers. NOT VERIFIED.

**10. Sensitivity. VERIFIED (code), policy is a PO decision**
Should not go to a phone in v1: `alerts.raw_text`; `intelligence_events` raw rows and
`score_breakdown`; `audit_events` rows (`briefs/[id]` returns them); `alert_sources`
feed URLs and notes; source `error_message` strings and job `lastAction` text (internal
failure detail); `operating-picture` `created_by` and mission lists; all health-OSINT
rows. Personal data on the allowlist:
`captains_daily_briefs.health_snapshot` is the Captain's own health/capacity data. The
Captain's own device viewing it is fine, but decide explicitly whether it goes in v1;
the recommendation is to omit it. Other people's data: none seen on these routes.
Cloud tier: the candidate read routes make no LLM calls (VERIFIED by reading them).
`captain-brief` and `briefs/domains` delegate to the context service, whose contents
I did not read (NOT VERIFIED), another reason to exclude them. A read-only snapshot
adds nothing to what is sent to any cloud model.

**11. Where does the portal run? Partly VERIFIED**
Two deployment targets exist. (a) Vercel team `usstjr`, project `usstjros` (domains
`usstjros.vercel.app`, `usstjros-usstjr.vercel.app`), latest deployment READY. The
existing middleware test uses `usstjros.vercel.app`. Two other Vercel projects exist
(`tjrmindbody`, `lcars-portal`, the latter last updated 2026-09-04). (b)
`deploy/lcars-portal.service` runs `next start -p 3200` behind Caddy on the VM, and
`auto-deploy.sh` rebuilds and restarts it. Which one serves the Captain's real traffic
is NOT VERIFIED; the code comments describe both ("frontend already closes this loop
via Vercel", "Caddy is the real front door"). The app's base URL decides the answer.
Vercel Deployment Protection (SSO or password) and firewall rules: NOT VERIFIED. The
project API returned no protection fields and the firewall config endpoint returned 404.
Because the ping route already exists, ask the iOS side whether a bearer call to it
has ever succeeded from the device against the intended host. That is the quickest
proof that nothing in front blocks a native client. Preview deployments are likely
behind protection and would need a bypass secret for testing.

### OPERATIONS

**12. Deploy impact. VERIFIED, with a warning**
- A change under `lcars-portal/` only rebuilds and restarts `lcars-portal.service`
  (`auto-deploy.sh:301-319`, staleness against `lcars-portal/` commits).
- `tg-capacitybot.service` is NOT in `deploy/auto-deploy-services.conf`, so
  auto-deploy never restarts it. Shared code with the bots: none (portal is TypeScript;
  bots are Python). The only coupling is shared Supabase tables and, for one route,
  `/api/google-tasks/sync` with a bot secret, which this change would not touch.
- **Warning:** the services in `auto-deploy-services.conf` (`context-service`,
  `intelligence-scheduler`, `mint-server`, `model-router`,
  `self-improvement-dashboard`, `tg-revs`, `tg-xo`) are restarted when the newest
  commit ANYWHERE in the repo is newer than their start time
  (`auto-deploy.sh` header). So ANY merge to `main`, including this docs-only report,
  causes those restarts at the next 5-minute tick. `intelligence-scheduler` owns the
  07:00 brief job. Hence: merge only in the PO window 14:30 to 16:30 Melbourne, and do
  not merge this report PR (or keep it out of main entirely).

**13. Kill switch.**
Design it in: (1) env var `MOBILE_BEARER_READ_ENABLED` must equal `true` and
`MOBILE_READ_CAPTAIN_USER_ID` must be set, else every bearer request gets 403, checked
in both middleware and helper. (2) Revoke the Captain's sessions in Supabase Auth
(also kills the phone). Speed: on Vercel an env change needs a redeploy or instant
rollback (minutes). On the VM it needs a service restart with the new Infisical value.
Neither is instant. If instant is required, add a flag in a store read per request
(extra cost; probably not worth it for one user). NOT VERIFIED which target is live,
so the real kill path depends on Q11.

**14. End-to-end verification without live sends.**
Unit and route tests with mocked `getUser` (no network, no Telegram involved; none of
these routes send anything). Manual test: the PO signs in on their own device with the
iOS build pointed at a Vercel preview URL or the VM; the token stays on the device and
is never pasted into chat, a ticket or a log. Nobody else supplies a token. Preview
deployments need the env vars set at Preview scope and any protection bypass handled
outside the repo. A synthetic check: call an allowlisted path with an invalid token
and with no header and confirm 401 JSON and not a redirect.

**15. Rollback and effort. Size M** (L if the snapshot route aims for full Captain's Chair parity)
Files touched (estimate): `middleware.ts`; `lib/supabase-server.ts` (or a new
non-`'use server'` `lib/captainBearer.ts` for the Edge-safe verifier); one new snapshot
route plus its response builder; `middleware.test.ts`; new route tests; `.env.example`
and docs. About 5 to 7 files, 15 to 25 tests. Rollback: revert the single PR (cookie
behaviour is unchanged by design) plus the kill switch above.

**16. Unsuitable candidates and why.**
- `/api/operating-picture`: reads a repo file via `REPO_ROOT` (fails or differs on
  Vercel), returns up to 200 missions with `created_by`, and its 500 path returns detail.
- `/api/captain-brief`, `/api/briefs/domains`: depend on the context service URL and
  secret, 15 s timeouts, in-memory rate limit; the Captain's Chair page itself calls
  `captain-brief` "known-fragile".
- `/api/health-osint/*`: raw OSINT rows, web-shaped; `intelligence-summary` reads a
  repo config file.
- `/api/emergency-alerts/silences`: same path handles POST; `/sources`: returns feed
  config.
- `/api/agent-status`: raw 40-job list; use the overview `captainSummary`.
- `/api/briefs` (list): 100 rows with jsonb; fine only with a "latest N" trim.
- Captain's Chair as a whole: no single route; needs the snapshot.

---------------------------------------------------------------------------

## 3. Recommended v1 allowlist (exact paths, GET only)

Option A, purpose-built (recommended for Captain's Chair and HQ status):
1. `GET /api/mobile/snapshot` (new, versioned payload, plain text, trimmed fields):
   command posture, needs-you list, emergency alerts summary, latest daily brief as plain
   text lines, HQ status `captainSummary`.

Option B, bearer on existing routes (small, low-risk, for detail views):
2. `GET /api/emergency-alerts` (add `fields` trim or cap rows to 50 for bearer callers)
3. `GET /api/captains-daily-brief` (drop `health_snapshot` for bearer callers, or
   confirm PO accepts it)
4. `GET /api/home/needs-attention`
5. `GET /api/agent-status-workbench/overview` (only if the snapshot does not cover it)
6. `GET /api/briefs/[id]` and a latest-1 variant of `/api/briefs`: defer to v2.

Exclude: everything in Q16, every POST, PUT, PATCH, DELETE, every path not
listed, and prefix or wildcard matching. Pin the list in a test.

## 4. Recommended auth design (confirms the hypothesis with changes)

- Middleware: for allowlisted exact paths with method GET and a well-formed
  `Authorization: Bearer` header, verify with `getUser(token)` and compare `user.id` to a
  dedicated `MOBILE_READ_CAPTAIN_USER_ID`. Do NOT reuse the health-bridge id, so that
  revoking one capability does not revoke the other. Any failure returns plain 401 JSON
  (403 if the id differs or the feature is off), never a redirect. All other paths keep
  today's cookie flow unchanged, including bearer requests to non-listed paths.
- Route level (defence in depth): a new async `requireCaptainRead(request)` that
  performs the same verification independently, used only by allowlisted routes.
  Leave `requireSession` untouched so none of the ~120 mutating routes become reachable
  by bearer.
- Data client: for bearer requests build the client with the Authorization header so
  the `authenticated` role applies. Do not use a service-role client for any allowlisted
  route.
- Response: `Cache-Control: private, no-store`; no raw database error text.
- Add an in-memory per-Captain rate limit (for example 30 requests/minute).

## 5. Test plan

Valid Captain token returns 200; other user's valid token returns 403; missing,
malformed, expired token returns 401 JSON (not 307); bearer on non-listed path keeps the
307 redirect; bearer on POST/PUT/PATCH/DELETE to a listed path is refused; allowlist
pinned by an exact-set test; feature flag off returns 403; env id unset returns 403;
cookie session behaviour unchanged for listed paths; one response-shape test per listed
route; snapshot payload has no excluded fields (`raw_text`, `health_snapshot`,
`error_message`); a test that `requireSession` itself is unchanged. Roughly 15 to 25 tests.

## 6. Open decisions for the PO

1. Independent security review of the auth change: **YES, recommended.** It is small
   but it changes the one boundary that guards a database whose policies are all
   `true`, and the existing middleware has had a real Edge-runtime failure.
2. Which host serves the app (Vercel `usstjros` or the VM behind Caddy) and has the
   health-bridge ping ever succeeded from the device against it?
3. Option A (snapshot), Option B (existing routes) or both for v1?
4. Is `health_snapshot` (the Captain's own health data) allowed on the phone in v1?
5. Who are the other 2 auth users, and is public sign-up disabled? Today any of them
   is "the Captain" in the cookie flow.
6. Fix the anon-readable `alerts`, `alert_sources`, `alert_silences`,
   `domain_heartbeats`, `intelligence_source_health` policies as a separate task?
7. Dedicated env var names and where they live (Vercel vs Infisical).

## 7. Risks, ranked

1. **Captain check is the only gate.** RLS is `true` for any authenticated user on all
   candidate tables; a bug in the id comparison exposes everything on the allowlist.
2. **Scope creep into `requireSession`.** Making it bearer-aware would open about 120
   mutating routes to bearer callers. Avoid.
3. **Any merge restarts bots.** `auto-deploy.sh` restarts `intelligence-scheduler`,
   `tg-xo`, `tg-revs`, `context-service` and others on any main commit; merge only in
   the PO window, clear of 07:00, 12:30, 18:00.
4. **Ambiguous production host and protection layer.** Deployment protection, firewall
   and the kill-switch speed are NOT VERIFIED.
5. **Payload and privacy:** unbounded fields (`raw_text`, `health_snapshot`, error text).
6. **Repo/live RLS drift:** migrations do not describe live policies.
7. **Pre-existing anon-readable tables** (not caused by this work).
8. **Token lifetime/refresh settings NOT VERIFIED;** a leaked token is valid until expiry.
9. **No effective rate limiting** beyond an in-memory limiter on two routes.
10. **Double Supabase Auth round trip** per request if both middleware and route verify
    (latency only).

## 8. Not verified (summary)

Typical payload sizes and latency (no production rows read); Vercel Deployment
Protection and firewall state; which host is live; JWT expiry and refresh settings and
sign-up setting; `HEALTH_BRIDGE_CAPTAIN_USER_ID` being set; context service internals;
`intelligence_briefs` text format; Caddy log contents; actual RLS-as-user behaviour of a
bearer client (standard Supabase behaviour, not executed here).
