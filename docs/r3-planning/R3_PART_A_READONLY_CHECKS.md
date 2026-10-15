# R3 Part A: read-only checks (H8)

Date: 2026-10-15. Requested by: TJR Life R-lead (iOS). Approver: PO (timjardenross).
Scope: read-only. No policy, setting, env var or data was changed. No token, secret or
message content is reproduced here. User identifiers are masked to 8 characters or fewer.

Labels: **VERIFIED** = read from the live system or code in this session.
**NOT VERIFIED** = could not be read from here, with the reason and who can check.

Targets read: Supabase project `USSTJR` (ref `cjvrpjwewsrumnbdydgg`, ap-southeast-1,
ACTIVE_HEALTHY) and Vercel project `usstjros` (team `usstjr`). The other Supabase project,
`TJR_jobvacancies`, is INACTIVE and was not read.

## Summary

| # | Check | Result |
|---|-------|--------|
| 1 | Public sign-up disabled | **NOT VERIFIED.** Auth settings are not readable from the tools available here. |
| 2 | Auth users and Captain | **VERIFIED** 3 users. Captain id **NOT VERIFIED** (value is write-only in Vercel). |
| 3 | Anon-readable tables | **VERIFIED.** 11 tables plus 7 views. Your 5 confirmed, plus 6 more. |
| 4 | JWT expiry / refresh rotation | **NOT VERIFIED.** Same reason as 1. |
| 5 | `HEALTH_BRIDGE_CAPTAIN_USER_ID` in production; host | **VERIFIED** set (sensitive). Host: both Vercel and the VM run this app. |
| 6 | Deployment protection / firewall | **VERIFIED** SSO protection is ON for `usstjros.vercel.app`. This is likely a blocker. Firewall **NOT VERIFIED**. |

## Findings that change the plan

1. **Vercel SSO protection is enabled** on `usstjros` (`ssoProtection: all_except_custom_domains`,
   VERIFIED via the project API). The iOS app hard-codes `https://usstjros.vercel.app`, which is
   not a custom domain. If Vercel Authentication applies to that hostname, the iOS bearer request
   gets Vercel's 401/SSO page and never reaches `middleware.ts`. Whether the production alias is
   exempt is **NOT VERIFIED**: the sandbox proxy blocks that host, so no live request could be
   made from here. **Action for PO**: from a phone off the VPN, `curl -i
   https://usstjros.vercel.app/api/integrations/health-bridge/ping` with no auth. A JSON 401
   from the app means unprotected. An HTML page or a `_vercel_sso_nonce` cookie means protected.
   The existing Health Bridge route has the same exposure, so this is also a question about
   whether Health Bridge works today.
2. **Authenticated is not Captain.** Nearly every table's policy for the `authenticated` role is
   `USING (true)`. Any account that exists in `auth.users` can read briefs, missions, health
   logs and so on through PostgREST. Sign-up being closed (check 1) is therefore the real
   perimeter for everything the bearer endpoint reads, and the `MOBILE_READ_CAPTAIN_USER_ID`
   comparison is the only per-user gate. Check 1 is the most important unresolved item.
3. **Unrecognised third account.** One of the three users was created 2026-09-20 and last
   signed in the same day (see check 2). If the PO does not recognise it, treat it as a
   sign-up leak and remove it.
4. **Anon can execute four SECURITY DEFINER delete functions** (`prune_audit_events`,
   `prune_core_events`, `prune_intelligence_source_health`, `prune_verification_state`).
   Anyone with the public anon key can call them via `/rest/v1/rpc/...`. They only delete rows
   older than a fixed horizon, so the impact is bounded, but anon should not run them.
   Separate issue.

## 1. Public sign-up

**NOT VERIFIED.** The Supabase tools here expose SQL, advisors and logs, not the GoTrue
settings (`disable_signup`, `external_email_enabled`, `mailer_autoconfirm`). The Supabase
Management API or the dashboard (Authentication > Sign In / Providers > "Allow new users to
sign up") is needed. `auth.audit_log_entries` is empty (no retention), so past sign-up events
cannot be inferred either. What was read: the 3 users have no `invited_at` and no
`confirmation_sent_at`, consistent with dashboard-created or auto-confirmed accounts. That does
not distinguish the two.

Related advisor warning (VERIFIED): leaked-password protection is disabled.

**Action for PO**: open the dashboard and confirm "Allow new users to sign up" is OFF. If it is
on, switch it off before the snapshot route is enabled in any environment.

## 2. Auth users

VERIFIED, counts and masked identifiers only:

| Masked id | Email (masked) | Provider | Created | Last sign-in |
|-----------|----------------|----------|---------|--------------|
| `c538f7b7…` | `ti***@outlook.com` | email | 2026-06-19 | 2026-10-11 |
| `4cad0c28…` | `ti***@outlook.sg` | email | 2026-06-27 | 2026-10-15 |
| `f7486ce9…` | `ti***@gmail.com` | email | 2026-09-20 | 2026-09-20 |

Total 3, all confirmed, none anonymous, none banned, none SSO, one identity each.

**Which is the Captain: NOT VERIFIED.** `HEALTH_BRIDGE_CAPTAIN_USER_ID` is stored as a Vercel
`sensitive` variable, which cannot be read back. Two accounts are in active use. The PO should
compare the id in Vercel with the masked ids above. `MOBILE_READ_CAPTAIN_USER_ID` must be set to
the Captain's full id from the dashboard, never copied from this report.

## 3. Anon-readable surface (public schema)

Method (VERIFIED): `anon` role grants plus `pg_policies`. Note that Supabase grants `anon` all
privileges on every public table by default, so grants alone prove nothing. RLS policies are
the control. A table is anon-readable only if RLS is off or a SELECT policy applies to `anon`
or `public` without an `auth.role()` condition.

**Tables with RLS on and an unconditional anon/public SELECT policy** (anon can read every row):

| Table | Policy | Note |
|-------|--------|------|
| `alerts` | `alerts_read` public `true` | In your list. Public emergency-alert data, but includes `raw_text`, lat/long. |
| `alert_sources` | `alert_sources_read` public `true` | In your list. Holds feed URLs and notes. |
| `alert_silences` | `alert_silences_read` public `true` | In your list. |
| `domain_heartbeats` | `domain_heartbeats_read` public `true` | In your list. Job names and last-action text. |
| `intelligence_source_health` | `anon_read` public `true` | In your list. Includes `error_message`. |
| `domain_registry` | `domain_registry_read` public `true` | **Additional.** |
| `emergency_alert_summary_state` | `..._read` public `true` | **Additional.** |
| `verification_state` | `verification_state_read` public `true` | **Additional.** |
| `architecture_records` | `anon_read` anon `true` | **Additional.** |
| `commander_decisions` | `anon_read` anon `true` | **Additional.** Likely the most sensitive of the extras. |
| `lessons_learned` | `anon_read` anon `true` | **Additional.** |

**Views readable by anon** (7, RLS cannot apply to views, but all have `security_invoker = true`
so they inherit the underlying table policies and are readable only where the base table is):
`content_pipeline_summary`, `domain_heartbeat_latest`, `domain_heartbeats_latest`,
`intelligence_source_health_latest`, `knowledge_hierarchy_summary`,
`knowledge_unmapped_missions`, `source_registry_by_tier`. Effective exposure depends on their
base tables and was not traced.

**Not anon-readable**: tables whose policy is `auth.role() = 'authenticated'` (the `health_*`,
`signal_*`, `validation_job_runs` family) return nothing to anon. Tables with RLS on and no
policy (36, listed by the advisor) deny everything except the service role and are fine.

**Proposed fixes (separate issues, not done):**

- A. Drop the anon/public read policies on `alert_sources`, `alert_silences`, `domain_heartbeats`,
  `intelligence_source_health`, `domain_registry`, `verification_state`, `commander_decisions`,
  `architecture_records` and `lessons_learned`, after confirming no unauthenticated browser
  client reads them (`lib/supabase-browser.ts` callers). The status page and Telegram bots may
  rely on some of these, so audit callers first.
- B. For `alerts`, decide whether it is intentionally public. If yes, create a column-limited
  view without `raw_text`, `latitude`, `longitude`.
- C. `REVOKE EXECUTE ... FROM anon, authenticated` on the four `prune_*` functions.
- D. Revoke default `anon` table grants in bulk, so a future table with a sloppy policy is not
  exposed by default.
- E. Turn on leaked-password protection.

## 4. JWT expiry and refresh rotation

**NOT VERIFIED.** Same limitation as check 1. Dashboard path: Project Settings > Auth >
"JWT expiry limit", and Authentication > Sessions for refresh-token reuse interval. Supabase
defaults are 3600 s expiry with rotation on and a 10 s reuse interval, but this project's values
were not read, so do not rely on the defaults. The iOS app should assume short access tokens
and rotate refresh tokens on every use, and must store the new refresh token before using the
new access token.

## 5. Production host and Captain variable

- `HEALTH_BRIDGE_CAPTAIN_USER_ID` is **VERIFIED set** in Vercel for `production` and `preview`
  (type `sensitive`, value not read). Whether it is set on the VM was **NOT VERIFIED**: the VM
  is not reachable from here. On the VM the portal runs under `deploy/lcars-portal.service`
  with `run-with-infisical.sh`, so its environment comes from Infisical.
- **Vercel**: project `usstjros` has a production deployment from `main`
  (`dpl_3JW5…`, READY, target `production`, created from the latest `main` commit). Domains
  `usstjros.vercel.app`, `usstjros-usstjr.vercel.app`, `usstjros-git-main-usstjr.vercel.app`. VERIFIED.
- **VM**: `deploy/lcars-portal.service` runs `next start -p 3200`, with Caddy in front
  (comment in the unit file). VERIFIED from the repo. Its public hostname is not recorded in
  the repo.
- **Which one the Captain uses day to day is NOT VERIFIED.** The iOS app targets the Vercel
  hostname, so for this feature Vercel is the host that matters. The kill switch must be
  applied there (see the S2a PR). Two hosts means two places to flip a flag, and an unset flag
  on the VM is the safe default.
- Vercel reports 100 variables returned and an unspecified number of hidden production
  variables (`hiddenProductionEnvCount`), so absence of `NEXT_PUBLIC_SUPABASE_URL` and
  `NEXT_PUBLIC_SUPABASE_ANON_KEY` in the visible list for production is not evidence they
  are unset. The middleware already depends on them.

## 6. Deployment protection and firewall (Vercel `usstjros`)

VERIFIED from the project API: `ssoProtection.enabled = true`, `deploymentType =
all_except_custom_domains`; `passwordProtection.enabled = false`; `trustedIps.enabled = false`.
No custom domain is attached, so every listed hostname is a `*.vercel.app` name. See finding 1.

Firewall: the active-config read returned 404 "Seawall Config not found". That means no custom
firewall configuration was ever published for this project, so only Vercel's platform defaults
(DDoS mitigation) apply. No custom WAF or rate-limit rules. **VERIFIED** that the API returns
no custom config. Whether Attack Challenge Mode is on was not read.

Also noted: the latest Vercel deployments from `claude/*` branches are previews with no
`target`; they sit behind SSO protection too.

## Not done

Live probe of `usstjros.vercel.app` (proxy blocked the host); dashboard-only auth settings;
VM environment; Attack Challenge Mode; tracing base-table exposure of the 7 anon views.
