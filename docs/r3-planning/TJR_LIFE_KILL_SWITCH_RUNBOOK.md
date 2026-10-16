# TJR Life bearer read: kill-switch runbook

Applies to `GET /api/integrations/tjr-life/v1/snapshot` (R3 S2a/S3). Status of this document:
nothing below has been executed. Every "measured" and "test result" cell is **NOT VERIFIED**
until the PO runs the test (the PO tests later; nothing here is guessed). No token or secret
belongs in this file or in any test record.

Labels: **VERIFIED** = read from code or the live system. **NOT VERIFIED** = not measured.

## Switch table

| Switch | Host | Variable / setting | Redeploy or restart needed | Measured propagation | Verification request | Rollback (switch back on) | Who and from where | Test result |
|---|---|---|---|---|---|---|---|---|
| A. Feature flag, Vercel | Vercel project `usstjros`, Production | `MOBILE_BEARER_READ_ENABLED` set to anything other than the exact string `true`, or deleted | Yes, redeploy (VERIFIED from code that the flag is read per request from `process.env`; Vercel applies env changes only to new deployments: **NOT VERIFIED** on this project) | **NOT VERIFIED** (not measured) | `curl -i -H "Authorization: Bearer <valid Captain token>" https://usstjros.vercel.app/api/integrations/tjr-life/v1/snapshot` expects `403 {"error":"Forbidden"}` | Set the variable back to `true`, redeploy | PO, Vercel dashboard (Project Settings > Environment Variables, then Deployments > Redeploy) | **NOT VERIFIED** |
| B. Feature flag, VM | VM `lcars-portal.service` (Caddy to :3200), env from Infisical | `MOBILE_BEARER_READ_ENABLED`, same rule | Yes, restart `lcars-portal` (portal restarts are inside the 14:30-16:30 Melbourne window unless an emergency) | **NOT VERIFIED** | Same request against the VM hostname (not recorded in the repo: **NOT VERIFIED**), expects 403 | Restore the Infisical value, restart `lcars-portal` | PO or the server owner, Infisical then the VM | **NOT VERIFIED** |
| C. Captain id unset | Either host | Delete `MOBILE_READ_CAPTAIN_USER_ID` | Yes, as A or B (VERIFIED from code: unset gives 403 from both layers) | **NOT VERIFIED** | As A, expects 403 | Re-add the Captain's full id from the Supabase dashboard (never from a report) | PO, same places as A or B | **NOT VERIFIED** |
| D. Revoke the Captain's sessions | Supabase project `cjvrpjwewsrumnbdydgg` | Authentication > Users > the Captain > sign out / revoke sessions | No (VERIFIED from code that every request calls `auth.getUser(token)`, so the auth server decides) | **NOT VERIFIED** (JWT expiry and caching behaviour of the auth server were not read; do not assume instant) | Same request with the old token expects 401 | The Captain signs in again on the phone | PO, Supabase dashboard | **NOT VERIFIED** |
| E. Previous deployment | Vercel `usstjros` | Promote the previous deployment (instant rollback) | No new build, but a promotion | **NOT VERIFIED** | As A | Promote the newer deployment | PO, Vercel dashboard | **NOT VERIFIED** |

Default state: the flag and the Captain id are unset in production today (stated in the S2a PR;
**NOT VERIFIED** against the live Vercel and Infisical values), so merging changes nothing until both are set.

## Test script for the PO (not run)

1. Record the start time. Apply switch A. Redeploy.
2. Send the verification request every 10 s until it returns 403. Record the elapsed time as
   the propagation figure. Repeat for switch D (expect 401).
3. Roll back, confirm 200 with a valid token, record the time.
4. Write the figures in the table. Do not paste tokens, response bodies or headers.

## Defence in depth: where it is partial

Two layers refuse bad callers: `middleware.ts` (layer 1) and `requireCaptainRead()` in the route
(layer 2). Both call the same function, `verifyCaptainBearer()` in `lib/mobileBearerAuth.ts`.

- **Independent (VERIFIED by test):** layer 1 alone refuses missing/invalid/other-user tokens,
  non-GET, query strings, a disabled flag and an auth outage. Layer 2 alone, with middleware
  bypassed, refuses the same cases. Each test runs one layer with the other absent.
- **Shared (partial, not independent):** the token verifier, the flag check and the Captain-id
  comparison are one implementation. A bug in `verifyCaptainBearer()` defeats both layers. A
  second, independently written check would be needed to remove that; it is not built.
- **Not shared:** the rate limit exists only in layer 2; the 405 and `Allow` header only in layer 1.
