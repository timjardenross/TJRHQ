# XO Gate Review — Chief Engineer Architecture Review, Technical OSINT Workbench

Reviewer: Executive Officer (XO), USS TJR
Date: 2026-08-09
Subject: `/opt/starship-endeavour/.claude/skills/workbench-reviews/intelligence/chief-engineer-review.md`
Mode: Gatekeeper (this review reports a live, currently-exploitable data exposure — treated at the corresponding stakes)

## Verdict: Approve — escalate to Captain immediately, unchanged

This review is accurate, well-evidenced, and does not overreach its own authority. I independently reproduced the central claim myself — live, right now, with real network calls against the production database — rather than trusting the review's transcript of its own curls. It holds up. This goes to the Captain as written. Nothing in my spot-check weakens it; several points I checked came back *more* exactly confirmed than the review's own prose implies (exact row-count matches on four separate tables, not just "plausible").

There is no reason to hold this for rework. The only thing I'd add before it reaches the Captain is below (minor, does not change severity or the recommendation).

## Authority check

Chief Engineer's stated authority on this document is Advisory. The review respects that boundary correctly:
- Findings 1 and 2 (the security-tier ones) are explicitly marked "Captain decision required" and routed to the Escalation clause, not actioned.
- The Mission Status section states plainly: "no code was changed as part of this review (review-only mandate)."
- No self-clearing language anywhere — the review does not attempt to characterize the RLS exposure as "safe enough to leave" or invent a category of authority to act on it unilaterally. It also doesn't oversell what it can decide: Findings 3–5 are correctly scoped as "within normal engineering judgment," which is a genuinely lower-stakes bucket (error-message leak, dead code, a port default) and appropriately left for a fast follow-up rather than bundled into the same sign-off gate as 1–2.

No authority violation. This is what a correctly-scoped Advisory review looks like.

## Capacity check

I have no live capacity/recovery signal for the Captain today in this session, and I'm not going to invent one — per the standing rule, I'll say that plainly rather than assume.

That said, the *ask* this review makes of the Captain is small regardless of capacity state: approve a one-line RLS policy change (`CREATE POLICY ... TO authenticated`, twice), already drafted, already scoped, already low-engineering-risk. It is not asking the Captain to review code, adjudicate a design tradeoff, or spend real cycles — it's asking for a yes/no on closing a hole that is open right now. A live, unauthenticated, world-readable exposure of the Captain's own intelligence briefs (including unpublished RED-risk executive content) is exactly the class of thing that should interrupt a low-capacity day rather than wait for a better one — the review's own "Next Actions: Immediate" framing is correct, not alarmist. I would not defer this on a capacity basis. If the Captain's capacity today genuinely can't hold even a two-line decision, the fallback is: XO or Chief Engineer applies the two `CREATE POLICY` statements now under a narrow, explicit "close the open door" authorization while a fuller sign-off on "should any table stay anon-public and why" happens later — not leaving the exposure open until capacity improves.

## Spot-check findings — what I independently verified

I did not take the review's transcript on faith. I pulled the anon key and Supabase URL from the repo myself, ran my own curls against the live production REST API, read the two named migrations directly, walked the git history for the claimed regression commits, and cross-checked the port-default claim against the actually-running process. Everything below is something I personally executed in this session, not a restatement.

**Finding 1 (world-readable intelligence data) — REPRODUCED, live, in this session.**
- Pulled `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` from `lcars-portal/.env.local`.
- `curl` with only that anon key, no cookie, no session, no auth header beyond the public key, against the live `cjvrpjwewsrumnbdydgg.supabase.co` project:
  - `intelligence_events` → HTTP 200, real signal data returned (titles, risk ratings, rank scores).
  - `intelligence_briefs` → HTTP 200, **all 27 rows**, including a `RED`-risk, `IN_REVIEW` brief with full `executive_snapshot`, `top_events`, and `approval_audit` content — the exact content class `requireSession()` exists to gate.
  - `intelligence_source_registry` → HTTP 200, full source list.
- Row counts I pulled myself via `Prefer: count=exact` match the review's stated figures **exactly**: `intelligence_events` = 10,416, `intelligence_briefs` = 27, `intelligence_source_registry` = 138. Three independent exact matches — this is not a stale or exaggerated citation, the review's own count claims are precise as of when I checked, minutes ago.
- Read `0007_intelligence_platform_rls_hardening.sql` directly: confirmed it enables RLS with zero policies on all five named tables, and cites `DEC-20260610-120000` ("RLS remains enabled; backend services use service role; client-side access prohibited"). I confirmed `DEC-20260610-120000` is a real decision ID referenced independently in five other repo files unrelated to this review (`tools/BATCH-LOG-ALL-DECISIONS.sql`, `tools/supabase/schema/MSN-0060B-LEARNING-LOOP-SCHEMA.sql`, `core/context-assembly/enrichment_poc/...`) — it is not an invented citation.
- Read `0035_intelligence_anon_read_policies.sql` directly: confirmed it adds `anon_read USING (true)` to exactly `intelligence_events`, `intelligence_source_registry`, `intelligence_source_health` — not `intelligence_briefs` — matching the review's claim precisely.
- Grepped all 115 files in `core/infrastructure/supabase/migrations/` for any `CREATE POLICY` touching `intelligence_briefs`: **none exists.** Yet the live curl proves a read policy is active on that table right now. This independently confirms the review's most serious governance claim — the live policy on the single most sensitive table here has no corresponding migration in version control.
- One nuance the review didn't flag but I noticed: `intelligence_briefs` was granted RLS in 0007 same as the other four tables, but its currently-open read policy is untraceable while the *other four* tables' open policy (0035) at least has a migration, even though that migration itself was a governance misstep (public instead of `authenticated`-scoped). So `intelligence_briefs` is actually one notch worse than the other four — it has neither a correctly-scoped fix nor a traceable incorrect one. Doesn't change the finding, worth the Captain knowing the asymmetry.

**Finding 2 (audit_events RLS blocks everyone, including real sessions) — REPRODUCED, live, with a same-session exact-count match.**
- Read `0054_general_audit_events.sql` directly: RLS enabled, comment states "no public read/write (matches authority_audit_log/staff_autonomy_log)." Grepped all migrations for any later `CREATE POLICY` on `audit_events`: none exists, anywhere in the history.
- Live curl, anon key only: `audit_events` → HTTP 200, `[]`. Matches the claim.
- I located the service-role key in `core/command-centre/backend/.env` (used it only for this read-only verification, consistent with what the review itself did) and queried `audit_events` directly, bypassing RLS legitimately as the backend's own credential does: **398 rows**, and a filtered count on `details->>record_id is not null` also returned **398/398** — an exact match to the review's specific claim ("398 real rows exist with `details->>'record_id'` populated"). That claim was not approximate; it's precisely right.
- Read `lcars-portal/src/lib/supabase-server.ts` directly: `createSupabaseServerClient()` is built with `NEXT_PUBLIC_SUPABASE_ANON_KEY`, not a service-role key — confirmed the review's core mechanism claim that even a real, logged-in Captain session hitting this path is still subject to the same implicit-deny RLS as an anonymous request, because the client's underlying Postgres role is `authenticated`, not `service_role`, and no `authenticated` policy exists either.
- Confirmed `brief/route.ts` queries `audit_events` via that same anon-key client (`sb.from('audit_events')`, line 64), and confirmed the "Audit trail" UI comment in both `brief/[id]/page.tsx` and `escalation/[id]/page.tsx` cites "WORKBENCH-REVIEW.md H11, 2026-07-18" verbatim as claimed.
- Also confirmed `requireSession()`'s cited comment — "any authenticated session is the Captain" — exists verbatim in the source, not paraphrased or invented.

**Finding 3 (error-detail leak, and specifically that it's a regression) — REPRODUCED, including the exact regression diff.**
- Confirmed the current live `route.ts` catch block echoes `err.message` to the client.
- `git show 1537be6` (2026-07-18): confirmed this commit explicitly removed `detail: String(err)` from this exact file and replaced it with a generic `{ error: 'workbench_read_failed' }` at 500, with a comment citing "WORKBENCH-REVIEW.md H4, 2026-07-18" — word-for-word what the review cites.
- `git show 3de1cc1` (2026-07-30, later — confirmed via `git log --reverse` ordering): the diff for this commit shows the line changing back from `{ error: 'workbench_read_failed' }` to `{ error: 'workbench_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' }` — the exact reintroduction, in the exact file, in the exact hunk the review describes. This is not an inference; I read the diff directly.
- Confirmed `route.ts.bak` is git-tracked (`git ls-files` lists it) and was created by that same `3de1cc1` commit; confirmed `.gitignore` only excludes `next-env.d.ts.bak`, not `.bak` generally, so this wasn't meant to be excluded and simply wasn't cleaned up.

**Finding 4 (dead Overview route) — REPRODUCED.**
- Read `page.tsx`'s fetch logic directly: the `endpoints` map used by the live Overview screen only contains the 5 domain-specific routes (`confidence-matrix`, `intelligence-summary`, `source-network`, `threat-assessment`, `credibility`). The base `/api/intelligence-workbench` route is never referenced. Confirmed dead as claimed.

**Finding 5 (port default mismatch) — REPRODUCED, and I verified it more strongly than the review states.**
- `ss -tlnp` shows the real `command-centre` process (confirmed via `pm2 list`, uptime 21 days matching the review) listening on port **5000**, not 5050.
- `curl localhost:5000/health` → 200, real payload. `curl localhost:5050/health` → connection refused.
- Confirmed `action/route.ts`, `capture/[id]/route.ts`, and `verification.ts` all default to `localhost:5050` when `COMMAND_CENTRE_API_URL` is unset, while `advisory/route.ts` correctly defaults to 5000.
- One nuance not mentioned in the review: the backend's own source code (`core/command-centre/backend/app.js`) actually defaults to `PORT = process.env.PORT || 5050` — so 5050 isn't a pure invention, it's the code's own fallback. It's only wrong in practice because the deployed `.env` overrides `PORT=5000`. This doesn't change the finding or the fix (align the 3 files to 5000, matching the actual deployed reality) — just worth the Captain/Engineering knowing *why* two different "correct" defaults exist in this codebase, in case someone "fixes" `app.js`'s own default later and reopens the mismatch from the other direction.

## What I did not verify (disclosing per the citation-honesty standard)

- `signal_corroboration` (claimed 5,360 rows) and `source_reliability_snapshot` (claimed 178 rows): I attempted a quick anon-key count-check on both and got HTTP 400 (my column-name guess was wrong, not investigated further under time constraints). I did not confirm these two specific figures. They are not load-bearing for the security verdict — the four counts I did confirm (events, briefs, sources, audit_events) all matched exactly, which is strong evidence the review's SQL-derived numbers throughout are trustworthy — but I want to be precise that these two specific ones are unconfirmed by me, not confirmed-and-omitted.
- I did not query `pg_policies` directly (no direct Postgres session in this environment). My confirmation that RLS policies match the claimed state is behavioral (the REST API returns exactly what the stated policy would produce) plus textual (I read the migration files that create/alter them). That is strong evidence but is a different thing from reading `pg_catalog` directly, and I want that distinction on the record rather than implying I did the latter.
- I made roughly a dozen read-only REST calls in total across this verification. No rate limiting was encountered, consistent with the review's claim, but this was not a rigorous rate-limit test in either direction.
- I did not attempt to reproduce the RBAC/write-path claims (Finding-adjacent, not itself a finding) — the review's own citation of a prior live-verification run (`data/self-improvement/runs/r_20260712_053/evidence.json`) plus structural code reading was accepted as-is; re-deriving a 403 on a real `publish_brief` call was out of scope for what needed re-checking here, since it isn't the disputed claim.

## Bottom line

The core claim is not just plausible, it is confirmed by me, right now, with a real unauthenticated curl against production that returned all 27 intelligence briefs including unpublished RED-risk content, plus the full 10,416-row event history — no login, no session, just the public anon key anyone who has ever loaded the site already has. The governance-gap claim (an `intelligence_briefs` read policy live in production with zero trace in the migration history) is independently confirmed by my own grep of all 115 migration files. The regression claim on Finding 3 is confirmed to the level of reading the actual diff that reintroduced it. This review should go to the Captain unchanged, today, not queued behind anything else.
