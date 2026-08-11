# Chief Engineer Architecture Review — Technical OSINT Workbench (Intelligence Workbench)

USS TJR · Registry USS-TJR-003 · Engineering Division · Advisory authority
Reviewer: Chief Engineer · Date: 2026-08-09
Scope: `/intelligence-workbench`, live at usstjros.vercel.app, registered in `lcars-portal/src/lib/workbenches.ts` as "Cyber, infrastructure, and regulatory signal intelligence — source reliability, confidence scoring, and threat escalation."

## Mission Summary

Perform a grounded, code-verified architecture review of the Technical OSINT Workbench: is what's shipped trustworthy, is the data it shows real, is the write path safe, and what's the actual risk profile of what's live right now.

## Assessment

### What's actually live

The workbench is two things wearing one name, both real:

1. **Overview screen** (`lcars-portal/src/app/intelligence-workbench/page.tsx`) — a 5-tab domain toggle (Confidence Matrix, Intelligence Summary, Source Trust Network, Threat Assessment, Signal Credibility), each backed by its own API route under `lcars-portal/src/app/api/intelligence-workbench/{confidence-matrix,intelligence-summary,source-network,threat-assessment,credibility}/route.ts`.
2. **Brief workflow** (`.../brief/[id]/page.tsx`, `.../escalation/[id]/page.tsx`) — a governed 3-gate approval flow (In Review → QA Passed → Published) plus a RED-escalation crisis screen, both reading `GET /api/intelligence-workbench/brief` and writing through `POST /api/intelligence-workbench/action`.

I read every file in both trees, the API routes and their Python backend (`intelligence/workflow/{service,repository,api,cli}.py`), the VM proxy (`core/command-centre/backend/api/intel-governance.js`), and queried the live Supabase project (`cjvrpjwewsrumnbdydgg`) directly — both via SQL and via unauthenticated REST calls with the public anon key — to verify claims rather than trust code comments.

**Data is real, not mock.** `intelligence_events`: 10,416 rows, 1,482 in the last 7 days. `intelligence_source_registry`: 138 sources. `signal_corroboration`: 5,360 rows. `source_reliability_snapshot`: 178 rows. `intelligence_briefs`: 27, of which exactly 1 has ever reached `PUBLISHED`. The 5 domain routes and the brief workflow query these tables directly with real filters (confidence scale, CVE/CWE exclusion, tiering) and several have inline comments documenting real bugs found and fixed against live data (e.g. `credibility/route.ts`'s confidence-scale fix, `threat-assessment/route.ts`'s window-scaling fix, `source-network/route.ts` reading real reliability-snapshot history instead of hardcoded trend placeholders). This is evidence of genuine iterative hardening against production data, not a demo.

**The write path is real RBAC, not decoration.** `action/route.ts` requires a session, injects the actor's role server-side (`ACTION_ROLE` map — the browser never asserts its own role), and proxies to the VM's Command-Centre backend (`core/command-centre/backend/api/intel-governance.js`, confirmed running via `pm2` on this host, uptime 21 days), which spawns `intelligence.workflow.cli`. Every mutating action (`qa_pass`, `publish`, `escalate`, etc.) calls `require(actor_role, action)` in `intelligence/workflow/service.py` before touching a row — e.g. `publish_brief` gates on `EXECUTIVE_APPROVER`. This matches the prior "brief.publish as analyst → 403" live-verification claim in `data/self-improvement/runs/r_20260712_053/evidence.json`, and I confirmed the gate is structurally present in the current code, not just in that one prior test run.

### Finding 1 (CRITICAL — security, escalate to Captain): the raw intelligence database is world-readable, no login required

I fetched directly against the production Supabase REST API using only the public anon key (the same key shipped in the browser bundle — no session, no cookie, no login):

```
curl "https://cjvrpjwewsrumnbdydgg.supabase.co/rest/v1/intelligence_events?select=event_id,raw_title,risk_rating,rank_score&order=rank_score.desc&limit=3" \
  -H "apikey: <public anon key>" -H "Authorization: Bearer <public anon key>"
```

returned real signal titles and scores. The same unauthenticated call against `intelligence_briefs` returned all 27 briefs, including `IN_REVIEW` / `overall_risk: RED` rows with real `executive_snapshot` text — the exact content the app's `requireSession()` gate exists to protect.

This is because `intelligence_events` and `intelligence_source_registry` carry an `anon_read` RLS policy with `USING (true)` (confirmed via `pg_policies`), and `intelligence_briefs` carries both `anon_read` and `auth_read`, also unconditional. `requireSession()` in `lcars-portal/src/lib/supabase-server.ts` is a real, correctly-implemented gate at the Next.js API layer — but it only protects requests that go through the Next.js app. The underlying Postgres RLS policy is the actual security boundary for anyone hitting Supabase's PostgREST endpoint directly, and that boundary is open. The app-level session check is not wrong, but it is not sufficient — it's a locked door in a wall that doesn't reach the ceiling.

**This is a regression from a deliberate, documented decision, not an oversight that was never addressed.** Migration `0007_intelligence_platform_rls_hardening.sql` explicitly enabled RLS with **zero policies** (implicit deny) on `intelligence_events`, `intelligence_source_registry`, `intelligence_source_health`, `intelligence_briefs`, and `ori_source_documents`, citing a ratified decision (`DEC-20260610-120000`: *"RLS remains enabled; backend services use service role; client-side access prohibited"*) and explaining that anon-key table privileges had previously let anyone with the public key mutate this data. Eighteen days later, migration `0035_intelligence_anon_read_policies.sql` added `anon_read USING (true)` back onto `intelligence_events` and `intelligence_source_registry`, with the stated reason *"RLS was enabled but no SELECT policy existed for anon role, causing the portal to return empty results."* That's a real symptom (the portal's session-aware client legitimately needs read access), but the fix chosen was full public exposure rather than a policy scoped to `authenticated`, which the portal's `requireSession()`-gated client would have satisfied just as well.

`intelligence_briefs`'s current `anon_read`/`auth_read` policies aren't traceable to **any** migration file in `core/infrastructure/supabase/migrations/` — I grepped the full migration set and `list_migrations()` against the live project for every commit touching that table; none creates these two policies. That means the live policy state on the single most sensitive table in this workbench (it holds RED-risk executive briefs) currently has no corresponding entry in version control. Either it was applied out-of-band directly against the database, or the migration that created it was later removed from the repo — both are governance gaps independent of the exposure itself.

**Practical severity:** this is a single-tenant platform (`requireSession()`'s own comment: "any authenticated session is the Captain"), so there's no other legitimate tenant whose data this exposes to *each other*. But the anon key is public by construction — anyone who has ever loaded `usstjros.vercel.app`, inspected the bundle, or found the Supabase project ref can pull the entire OSINT signal history and every intelligence brief (including unpublished RED-risk ones) with a single unauthenticated curl command, no rate limit encountered in my test. This is a live, currently-exploitable data exposure today, not a theoretical one.

### Finding 2 (HIGH — a claimed fix doesn't work): the Audit Trail card is dead on arrival, for everyone, including legitimate sessions

`audit_events` has RLS enabled with **zero policies at all** (confirmed via `pg_policies` and Supabase's own advisor: *"Table `public.audit_events` has RLS enabled, but no policies exist"*). I verified empirically: the same unauthenticated REST call against `audit_events` returns `[]`, even though a service-role query confirms 398 real rows exist with `details->>'record_id'` populated.

This isn't just an anon-access gap — implicit-deny RLS with no policies blocks **every** role that isn't `service_role`, including `authenticated`. `brief/route.ts` reads `audit_events` using `createSupabaseServerClient()`, which is the session-aware **anon-key** client, not a service-role client. That means a real, logged-in Captain session hitting the Brief Review or Escalation page will *also* get zero rows back from this query — RLS filters silently, it doesn't error, so the API returns `{ audit: [] }` and the UI's `{auditTrail.length > 0 && <Card title="Audit trail">...}` block never renders.

The code comments on both `brief/[id]/page.tsx` and `escalation/[id]/page.tsx` explicitly describe this as a fix: *"Audit trail — fetched by the brief API since it was built, never rendered until now (WORKBENCH-REVIEW.md H11, 2026-07-18)."* Based on the live RLS state, that fix does not actually work in production — the feature was wired up at the frontend/API-call level, but the database policy needed to let the app's own client read the table it now fetches was never added. This is exactly the kind of "verify, don't trust prior claims" case the Chief Engineer discipline exists to catch: the fix is real code, genuinely committed, and still non-functional today.

### Finding 3 (MEDIUM — info disclosure): every read route in this workbench leaks internal error detail to the client

All 6 GET routes I read (`route.ts`, `confidence-matrix`, `credibility`, `intelligence-summary`, `source-network`, `threat-assessment`) share the same catch-block pattern:

```ts
return NextResponse.json(
  { error: 'matrix_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
  { status: 500 },
);
```

`err.message` on a Supabase query failure typically contains raw Postgres error text — column names, table names, constraint names. This is session-gated (only reachable by a logged-in session), so the practical blast radius is small on a single-tenant platform, but it's a real repo-wide pattern, not a one-off, and it's a regression on `route.ts` specifically: `1537be6` ("fix: session auth on 11 unguarded routes, stop masking read errors as 200") deliberately stopped echoing `err.message` on this exact file, and the later `3de1cc1` ("Implement Intelligence Workbench Phase B") reintroduced it — visible directly in the diff between the live `route.ts` and its own sibling `route.ts.bak`, which still carries the fixed version and the comment explaining why detail shouldn't be echoed.

### Finding 4 (notable, no user impact): the entire "Overview" API + its safety net are dead code

`api/intelligence-workbench/route.ts` (domain-aware Operational/Health overview, 193 lines) is not called from any page in the frontend — the live Overview screen (`page.tsx`) calls the 5 domain-specific routes instead. `route.ts.bak` (155 lines, committed and tracked in git, not gitignored) is a superseded backup of the same route created by the same commit that overwrote the live one. Two test files (`__tests__/operational-signals.test.ts`, `__tests__/health-insights.test.ts`) test hand-duplicated filter/sort logic inline in the test file rather than importing and calling the actual route handlers — so neither test can catch a regression in the real `route.ts`, and neither would have caught Finding 3's regression. None of this is reachable from a user's browser today, so it's not a live-trust issue, but it is ~350 lines of routing logic plus two test files that look like real coverage and aren't. Worth noting: the dead `route.ts`'s operational-signal query itself has the same 0–1-vs-0–100 confidence-scale bug that `credibility/route.ts`'s own comment says was found and fixed elsewhere (`MIN_CONFIDENCE = 60` compared against a column whose observed max is `0.98`) — meaning if this dead code were ever reconnected without re-review, it would silently return zero signals.

### Finding 5 (LOW — tech debt, no live impact): default proxy port disagrees with the actual VM service

`action/route.ts`, `capture/[id]/route.ts`, and `lib/verification.ts` all default `COMMAND_CENTRE_API_URL` to `http://localhost:5050/api/v1` when the env var is unset. The real Command-Centre backend (confirmed via `pm2 show` and a live `/health` check) listens on port **5000**, matching the default already used correctly in `api/advisory/route.ts`. Because Vercel's production deployment must have `COMMAND_CENTRE_API_URL` set explicitly (a `localhost` default is never reachable from Vercel's network regardless of port), this default only bites a developer running the portal locally without the env var set — and even then, `action/route.ts`'s own fallback logic (spawn Python directly) absorbs the failure. Low severity, but it's an unforced inconsistency across 3 files that should agree with the 4th.

## Recommendations

Ordered by priority — 1 and 2 are security-tier and route through the Escalation clause below, not a build-it-myself decision.

1. **[Captain decision required] Close the anon-read exposure on `intelligence_events`, `intelligence_source_registry`, `intelligence_briefs`.** Replace `anon_read USING (true)` with policies scoped to `authenticated` (the portal's session-aware client already authenticates as `authenticated` once a Captain session exists — no functional change to the app), or, if any genuine reason exists for public anonymous read (I found none in the code — `requireSession()` gates every route that touches these tables), that needs to be an explicit, current, re-ratified decision, not an unreviewed policy with no traceable migration.
2. **[Captain decision required, paired with #1] Add an `authenticated`-scoped SELECT policy to `audit_events`** so the already-shipped Audit Trail UI actually works for real Captain sessions, and confirm whether `health_source_articles` (same zero-policy state) needs the same treatment for the health-mode branch of this workbench.
3. Stop echoing `err.message` to the client across all 6 GET routes in `api/intelligence-workbench/` — match the pattern already correctly used in `brief/route.ts` and `action/route.ts` (log server-side, return a generic error code). This is a same-day, low-risk fix once 1–2 are decided (it's not gated by them).
4. Delete `route.ts.bak` and the base (dead) `route.ts` + its two tests, or reconnect `route.ts` to a real caller if the domain-toggled Operational/Health Overview screen is still wanted — don't leave a plausible-looking but untested and partially-buggy route sitting in the tree. If reconnected, fix the 0–1-vs-0–100 confidence bug in `getOperationalData` first (same class of bug `credibility/route.ts` already fixed once).
5. Align the `COMMAND_CENTRE_API_URL` default across `action/route.ts`, `capture/[id]/route.ts`, and `verification.ts` to port 5000, matching `advisory/route.ts` and the real running service.

## Next Actions

- Immediate: bring Findings 1 and 2 to the Captain as a paired RLS-policy change (both are one-line `CREATE POLICY ... TO authenticated` statements once approved — the engineering lift is trivial, the decision is what needs sign-off, per the "no carve-out for small platform-wide changes" rule).
- Once approved: apply the policy migration, re-run the same unauthenticated curl checks used in this review to confirm closure, then re-verify the Audit Trail card renders for a real session on both `/intelligence-workbench/brief/[id]` and `/intelligence-workbench/escalation/[id]`.
- Separately (no sign-off needed, low-risk): fix Finding 3's error-detail leak and Finding 5's port default in the same pass.
- Separately (no sign-off needed): decide keep-and-reconnect vs. delete for Finding 4's dead route + tests, then act on it.

## Mission Status

Advisory only. Findings 1 and 2 are security-tier and explicitly escalated to the Captain per the Chief Engineer escalation clause — not decided or actioned here. Findings 3–5 are within normal engineering judgment and can proceed once flagged, but no code was changed as part of this review (review-only mandate).
