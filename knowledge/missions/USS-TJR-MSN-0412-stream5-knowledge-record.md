# USS-TJR-MSN-0412 Stream 5: cloud-LLM redaction (knowledge record)

2026-10-09. Labels: MEASURED / INFERENCE / TO BE VERIFIED. Counts and sizes only.

## Decision
One rule: nothing goes to any cloud model unredacted. The earlier idea of an allowlist for `glm-*:cloud`
was dropped in favour of guarding that route the same way as the others (Captain's decision, 2026-10-09).

## What changed (PR #359, draft)
* `core/llm/provider_chain.py`: `call_gemini` / `call_mistral` run input rail, one Presidio redaction over
  system + user prompt, then the output rail on the reply. Fail closed: guard unavailable or busy, block,
  text over 150,000 characters (spaCy E088 limit is 1,000,000; redaction time is the practical limit), or a
  mangled part boundary all raise and nothing is sent. An inter-process lock serialises guard calls.
* `core/model-router/app.py`: any `*:cloud` model gets `secure_outbound_prompt` before and
  `check_output_rail` after, like the Gemini branch. Local models unchanged.
* Tests: 18 (provider chain) + 5 (router cloud route); 4 of the 5 router tests fail on the old code.

## Cost (MEASURED on the CPU-only host)
Redaction about 8 s, input rail 21-60 s, output rail about 16 s: roughly 45-90 s added per cloud call.
Redacting a 200,000-character text took about 190 s. About 17 call sites are affected, including both
health-osint tools and REVS `crisis_layer2` (see `telegram-bots/revs/README.md`).
Live smoke test through the real guard to the real provider: only `<PERSON>`, `<EMAIL_ADDRESS>` and
`<PHONE_NUMBER>` left the host (48 s).

## Incident: Supabase egress restriction, 2026-10-02 to 2026-10-05
**What happened (MEASURED):** Supabase restricted the whole project for `exceed_egress_quota` (Free plan,
5 GB cap) from about 2026-10-02 09:32 to 2026-10-05 19:13 AEDT. While restricted, API calls returned an error
body that made the Supabase client library raise instead of returning data.

**Impact (MEASURED, journal counts):** six services logged the failure, among them `command-bus` (9,697
lines), `tg-revs` (4,997) and `intelligence-scheduler` (1,414). It explains `health-signal-curation`
showing no calls since 2026-09-27 and the 2026-10-04 weekly fetch crashing after 13 s, so curation never
started that week.

**Why curation was quiet, in order:**
1. 2026-09-20 and 2026-09-27: curation ran past its 900 s limit and was killed (fixed by #350 on 2026-10-08).
2. Last successful curation: 2026-09-13 02:06.
3. 2026-10-04: the weekly fetch crashed on the restriction above.
4. Next weekly run: Sunday 2026-10-11 about 03:00 AEDT; the restriction has lifted, so it should run
   (TO BE VERIFIED after that run).

**Cause (INFERENCE):** sustained read volume from many services plus the weekly/bulk jobs. The nightly
backup dump (about 70-118 MB) and the Stream 4 test dumps on 2026-10-09 add to the same cycle, so they are
a new contributor from 2026-10-09 on. Real usage figure: from the Captain's Supabase dashboard (TO BE
VERIFIED; not readable from this host).

**Response:** Supabase dump moves to every 3 days and skips the regenerable log tables (see the egress PR);
the egress figure itself cannot be added to the weekly line from this host (no Management API token).

## Follow-ups
* Confirm the first post-restriction weekly fetch and curation run (2026-10-11).
* Decide the REVS crisis fallback for a refused or slow guard before REVS goes live.
* Consider an alert when a service sees the restriction error body (it was silent for 3 days).
