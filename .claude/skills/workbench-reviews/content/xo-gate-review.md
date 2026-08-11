# XO Gate Review — Chief Engineer Architecture Review, Content Workbench

USS TJR · Gatekeeper pass on `.claude/skills/workbench-reviews/content/chief-engineer-review.md`
Reviewer: XO · Date: 2026-08-09

## Verdict: Approve

The review holds up. I independently re-derived every load-bearing claim against the actual repo (not just the files the review cites — I read them myself) and, for the claims made against the live Supabase project, against the live project itself. Nothing I checked contradicted the review. This clears the gate as written; see the two small notes below (neither is a Hold condition).

## Authority check

Chief Engineer's documented authority is Advisory only (confirmed in `.claude/skills/chief-engineer/SKILL.md:8` and `specialists/core-crew/Chief-Engineer.md:5` — "Registry USS-TJR-003, Engineering Division, Advisory authority"). The review stays inside that line: it explicitly states "I have not made any code changes; this is Advisory only per my authority," and `git status` on the repo shows no modifications to any content-workbench file from this review pass. It does not self-clear any part of its own findings as "safe enough to just do" — recommendation #1 (the RLS fix) is flagged as low-risk but still handed to the Captain as "just needs a go-ahead," not silently applied. No invented hybrid-authority language, no scope creep. Clean on this axis.

## Capacity check

I have no live capacity/recovery signal for the Captain today in this session — saying that plainly rather than guessing. On the substance: the two items the review marks as the immediate next actions are genuinely small — a one-line client swap in `revisions/route.ts` and a comment-only edit in two files — low-risk, single-file-family, no schema or behavior change. That's a fit for almost any capacity level, but it's still the Captain's call on timing, not mine to assume "so just do it now."

## Spot-check findings

I re-checked every claim that carries weight in this review, not just the ones flagged as most novel. Summary: **everything held up exactly as stated.**

**RLS / revision-history bug — confirmed at both the code level and live DB.**
- Code: `revisions/route.ts` GET handler uses `createSupabaseServerClient()` (session client); `generate/route.ts` and `draft/route.ts` both use a hand-rolled `serviceClient()` (service-role key). Confirmed by reading all three files directly.
- Migration: `core/infrastructure/supabase/migrations/0095_content_workflow_extensions.sql` does `ALTER TABLE comms_content_revisions ENABLE ROW LEVEL SECURITY` with the comment "No anon policy: mirrors comms_content's own write pattern (service-role client only...)" — confirming the write-side assumption the GET route violates.
- **Live DB — I have Supabase MCP access to the same project (`cjvrpjwewsrumnbdydgg`, org USSTJR) and queried it myself, not just trusted the review's transcript of it:**
  - `pg_class.relrowsecurity = true` on both `comms_content` and `comms_content_revisions` — confirmed.
  - `pg_policies`: exactly one row, `comms_content` / `auth_read` / SELECT / `authenticated` / `qual: true`. Zero rows for `comms_content_revisions` — confirmed no policy exists.
  - `select count(*), count(distinct content_id) from comms_content_revisions` → 10 rows, 5 distinct items — matches the review's numbers exactly.
  - `select status, count(*) ... where status in ('review','ready_to_publish')` → 3 + 1 = 4 — matches the review's "4 items currently sitting in review/ready_to_publish" exactly.
  - This is a case where the task briefing anticipated I might lack equivalent DB access and told me to hedge if so — I didn't need to; I queried the live project directly and the numbers match to the row. I'm stating this as directly verified, not re-asserted secondhand.

**QA-gate-is-UI-only claim — confirmed.** Read the full `POST` handler in `api/comms/[id]/advance/route.ts` end to end: the `TRANSITIONS` map allows `review → approved` on `captain_approved` unconditionally; the handler only ever reads/writes `status`, never `qa_status` or `qa_checklist`. Migration 0095's `comms_content_qa_status_chk` constraint only validates the enum's own three values, not any cross-field invariant with `status`. The review's framing — real UI gate, no server-side or DB-level enforcement — is accurate, not overstated.

**Stale "Decide" comments — confirmed verbatim.** Both quoted passages exist exactly as cited: `page.tsx:17-18` ("the Captain approves the actual publish in Decide, same as always") and `route.ts:8-11,18-22` ("the Captain still makes the final call in Decide" / "awaiting the Captain's sign-off in Decide"). Cross-checked against commit `9fb2640` directly (`git show --stat` + full commit message) — the commit is real, dated 2026-08-08, and its message confirms the root cause exactly as the review describes: `mark_published` queued a proposal into a Decide queue nothing ever drained, because `/decide` doesn't exist and `/decisions` is a retired stub. I read that stub myself (`app/(app)/decisions/page.tsx`) — it says "This page moved... to /decide," which doesn't exist anywhere under `app/` (only unrelated `self-improvement/decide` and `knowledge-library/.../decide` routes do). `advance/route.ts`'s current header comment and `ContentBoard.tsx:456-461` do carry the corrected, accurate description ("mark_published is a direct flip again now") — so the review's claim that the fix commit touched those two files but missed `page.tsx` and the board's `route.ts` is exactly right.

**Auth gating — confirmed.** All 9 files under `api/content-workbench/**/route.ts` import and call `requireSession()` (verified via `grep -rL` finding zero files missing it). `advance/route.ts` also calls it. `PUBLIC_ROUTE_ALLOWLIST` in `lib/public-site.ts` does not include `/content-workbench`, so the global middleware redirect applies.

**Test coverage claim — confirmed.** `contentScoring.test.ts` exists, 98 lines. `DomainToggle.test.tsx` exists alongside `DomainToggle.tsx`. Repo-wide search for test files referencing `content-workbench` or `contentScoring` returns only the one scoring test — no route or component tests exist for this workbench, as claimed.

**"Two code paths can flip status" claim — confirmed.** Both `api/content-workbench/[id]/generate/route.ts:127` and `api/comms/generate/route.ts:111` write `status: 'draft'` directly via their own service-role update, bypassing `advance()`'s `TRANSITIONS` map, while `research/route.ts:8` explicitly comments "advance() stays the only place status transitions happen." The review's characterization (intentional, low-harm, but a live exception to a claim repeated elsewhere) is accurate.

**Registry tile — confirmed accurate**, both by reading `lcars-portal/src/lib/workbenches.ts:34` directly (current wording makes no Decide claim) and by the fact that the drift the review found is scoped correctly — it's in source comments, not the registry.

### One thing the review didn't flag, worth a mention

While reading migrations I noticed **two files both numbered 0095** in `core/infrastructure/supabase/migrations/`: `0095_content_workflow_extensions.sql` (the one this review relies on) and `0095_technical_osint_workbench_gaps.sql`, timestamped an hour apart the same day. Not a defect in anything the Chief Engineer reviewed, and not something that changes this verdict — but this platform has a documented history of exactly this kind of numbering collision causing real reconciliation pain (see memory: mission-ID minting drift, recurred more than once). Worth a cheap sanity check that both migrations actually applied cleanly and in the intended order, next time anyone's in that directory — not urgent enough to hold this review for.

## Recommendation to the Captain

Approve the review as delivered. The two "immediate, concrete" fixes it proposes (revision-route client swap; stale-comment cleanup) are small, correctly scoped to Advisory authority, and everything they're justified on has now been checked twice — once by Chief Engineer, once by me, independently, including live against the database both claims about it. Go-ahead on those two is a reasonable ask; the P3 QA-server-enforcement question is correctly left as a Captain decision, not a recommendation either way beyond "pick one so the registry description stays honest."
