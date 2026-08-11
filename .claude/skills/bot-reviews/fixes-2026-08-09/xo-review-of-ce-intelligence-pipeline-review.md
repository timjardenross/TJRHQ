---
title: XO gatekeeper review — Chief Engineer's whole-architecture review of tonight's intelligence pipeline
date: 2026-08-10
author: XO, USS TJR — Gatekeeper mode
scope: Independent verification of chief-engineer-intelligence-pipeline-review.md
  against live host state, live Supabase data, and the actual repo code — not a
  re-review of tonight's individual missions' own reports.
status: Advisory. Verdict below on each of CE's findings.
---

# Verdict summary

| CE Finding | Verdict |
|---|---|
| 1. Restart-gap (nothing running) | **Confirmed, and now genuinely resolved** — verified beyond what CE's own report checked |
| 2. Source Fidelity Audit field-mismatch bug | **Confirmed exactly as described** — read both files, bug is real |
| 3. Downdetector cadence undercuts its purpose | **Confirmed real, judged an acceptable disclosed trade-off for now** |
| 4. Report-count floor applied uniformly across sectors | **Confirmed real, genuinely the whole defense for banking/gov** — agree with CE this needs a decision, not an emergency |
| 5. CSV/DB/report three-way drift on the 9 banking/gov sources | **Confirmed real and still live right now** — plus a governance gap CE didn't have time to chase down, which I did |
| Found something CE missed | **Yes, two things** — see below |

Nothing here is a Hold. CE's engineering and CE's own recommendations both check out. The one thing I'd add to the Captain's plate that CE's report doesn't say explicitly: the 9 banking/government sources went live in production *without* the verification step their own build report said was the bar for flipping `active=true` — I ran that verification myself just now, so the outcome is fine, but the process gap is real and worth naming.

---

# 1. Restart-gap — CONFIRMED, and independently verified resolved

CE's own recommendation was "restart, then re-check the next collection cycle's health rows... confirm at least one real (non-example.com) external_fetch_usage increment." That's the right bar. I did more than re-check logs — I ran the actual production fetch paths myself.

**Restart timing, verified directly:**
```
$ systemctl show intelligence-scheduler.service -p ActiveEnterTimestamp
ActiveEnterTimestamp=Mon 2026-08-10 12:57:46 AEST
```
`journalctl` confirms a clean stop/start at that exact timestamp, PID 1593297. Every commit CE listed (guards 5/6, Downdetector adapter, Bright Data path, hard-cap breaker, all landing between 09:50 and 12:17 AEST) is now behind this restart. CE's own review commit (`85061441`) is too.

**New code is genuinely executing, not just present in the process image.** The post-restart log shows `intraday_status_collection` firing immediately (`next_run_time=now`) and logging "excluded 16 Firecrawl-fetch-path source(s)" — that number only makes sense post-tonight's-changes (14 active Downdetector sources + Fastly + AEMO Market Notices = 16; pre-restart code had zero Downdetector sources registered in the exclusion path at all). Collection completed cleanly: 465 items from 29 sources, 28 ok / 1 failed (Telstra, the known auth-gated source, expected).

**Where I went further than CE's own recommendation:** the paid-fetch code paths (Firecrawl 403-fallback, Bright Data 403-fallback, the hard-cap breaker) hadn't actually been exercised by the live schedule yet at the time I checked — `_daily_collection_job` (the job that touches Fastly/AEMO/Downdetector) doesn't run again until 06:00 AEST tomorrow, and the intraday job correctly excludes those sources by design. `external_fetch_usage` still showed only the 2 pre-restart smoke-test calls (1 each, both 02:15 UTC, both against `example.com`). So as of the restart alone, finding 1's *substance* — "does the new code actually work under production conditions" — was still unconfirmed, only "the process is now running the new code" was.

So I called the actual production modules directly, via the real venv (`platform-runtime/.venv/bin/python`), the same import paths the scheduler uses:

```
>>> firecrawl_client.fetch_html('https://www.fastlystatus.com/incidents')
LENGTH: 261785   (real page, not a 403 or challenge page)

>>> brightdata_fetch.fetch_html('https://downdetector.com.au/status/national-australia-bank/')
LENGTH: 339914   (real Downdetector page)

>>> downdetector_adapter.parse_status_and_count(html)
status: no_problems  count: 4   (plausible quiet-day NAB reading — CE's own report cites NAB's live baseline as 3)
```

`external_fetch_usage` incremented for real on both calls (brightdata 1→3, firecrawl stayed within its 1000/month ceiling by 1) — confirming `check_and_increment()` fires correctly on genuine calls, not just the smoke test.

**Verdict: resolved.** Not merely "the daemon restarted" — I have first-hand proof the two paid fetch paths that finding 1 said were "dormant" now genuinely return real content through the real code the scheduler will call at 06:00 tomorrow. This is stronger evidence than either CE's report or the restart alone provided.

One thing still open, cheap to close: the Bright Data Web Unlocker zone (`web_unlocker1`) is confirmed provisioned (`GET /zone/get_active_zones` returns it) — the account-side blocker `brightdata-provisioning.md` described is genuinely gone. Good.

---

# 2. Source Fidelity Audit field-mismatch — CONFIRMED, exact bug as described

Read both files directly, not summarized.

`intelligence/scheduler.py::_source_fidelity_audit_job()` (lines 916–923):
```python
report = source_fidelity_report(days=30)
total_sources = report.get("total_sources", 0)
high_value = len(report.get("high_value_sources", []))
low_value = len(report.get("low_value_sources", []))
degraded = len(report.get("degraded_sources", []))
```

`intelligence/audit/source_fidelity.py::source_fidelity_report()` (lines 104–166): builds `report = {..., "sources": {}, "summary": {}}`, then writes `high_value_sources` / `low_value_sources` / `degraded_sources` **only** into `report["summary"][...]` (line 157 onward). There is no top-level key by those names anywhere in the return value.

`total_sources` is the one field that *is* top-level and reads correctly — everything else in the log line is a silent `.get(..., [])` fallback to empty, every single day, at 06:45 AEST, `status="ok"` regardless. Confirmed byte-for-byte as CE described. Pre-existing (file dated 2026-07-30, untouched tonight), now load-bearing exactly as CE said — it's the only automated visibility mechanism into whether tonight's new sources are healthy.

**One thing worth adding:** this job is scheduled for 06:45 AEST, and the restart happened at 12:57:46 — meaning it will run for the first time on the new code at 06:45 tomorrow morning, still carrying this bug. Tomorrow's audit will log "0 degraded, ok" no matter what tonight's new sources actually do overnight. The one-line fix CE recommends (read `report["summary"][...]`) is genuinely a five-minute change; if it lands before 06:45 AEST tomorrow, tomorrow's audit becomes real instead of another day of false-clean.

---

# 3. Downdetector's once-daily cadence — CONFIRMED real, judged acceptable for now

Confirmed in `intelligence/scheduler.py`: `_excluding_firecrawl_fetch_sources()` (line 572) filters `source_type == "downdetector"` (all of it, not just banking/gov) out of the 180-minute intraday job. Downdetector only runs via `_daily_collection_job` at 06:00 — once/day, exactly as CE described, while the vendor status pages it's meant to complement run ~8x/day via the intraday job.

My own read on the trade-off, not just repeating CE's framing: the math genuinely doesn't work any other way on the current budget. Every Downdetector check plain-fetches first and only pays a paid-provider credit on the (confirmed, reliable) Cloudflare 403 — meaning nearly every check against these 19 sources costs one Firecrawl or Bright Data call. At 8x/day instead of 1x/day: the 10 telecom/other sources alone would be ~2,400 Firecrawl calls/month against an 850 safe ceiling — blows the budget by nearly 3x on this source type alone, before counting the 7 other sources already on that fetch path. Bright Data's larger ceiling (4,500) could plausibly absorb 8x for the 9 banking/gov sources (~2,160/month) with room to spare, so a narrower fix — intraday cadence for banking/gov only, daily for telecom/small-ISP — is mathematically available within Bright Data's own headroom without touching the Firecrawl-constrained side at all. I'd flag that as a genuine option CE's report doesn't surface (CE frames it as an all-or-nothing "5 core-telecom sources" question against Firecrawl headroom — there's a second, cheaper lever on the Bright Data side that doesn't compete with Firecrawl's tighter budget at all).

Not urgent tonight. Worth a real decision from the Captain, not a silent default to "we'll get to it."

---

# 4. Uniform 150-report floor across sectors — CONFIRMED, genuinely the sole defense for banking/gov

`_REPORT_COUNT_FLOOR = 150` (single constant, `downdetector_adapter.py` line 66) applies identically regardless of sector. Confirmed the guard-bypass too, directly in `intelligence_store.py::_maybe_push_outage_alert()` (lines 534–544): Downdetector-sourced events explicitly skip both `_passes_vendor_tier_gate()` and `_passes_blast_radius_check()` — the two guards protecting every other source. The reasoning in the dated comment is sound (both guards would wrongly suppress genuine Downdetector-confirmed bank/government outages), and I agree with CE that the bypass itself is the right call — Finding 7 in CE's report holds up.

That leaves the floor as the only thing standing between a real event and a push alert for these 9 sources. CE's own live sample (which I didn't re-pull but have no reason to doubt, given how directly it's grounded in the adapter's own baseline documentation) shows banking/government baselines 5–10x lower than telecom's — meaning a proportionally severe bank outage plausibly never clears 150.

Agreed with CE's overall framing: not an emergency, but this is the one place in tonight's build where "first-cut, needs calibration" quietly became "the only thing this source type has." Worth a per-sector floor (or at minimum a lower interim number for banking/government) before the Captain treats a Downdetector-sourced banking alert's *absence* as meaningful — right now it plausibly isn't.

---

# 5. CSV/DB/report three-way drift — CONFIRMED real and still live, plus a governance gap CE didn't chase down

**Confirmed independently, right now, via live queries — not from the reports' own claims:**

Live `intelligence_source_registry` (queried directly):
```
Downdetector AU — NAB / ANZ / CBA / Westpac / Bendigo / UBank / MyGov / Centrelink / myID
  → all 9 active=true
```

`tools/intelligence/sources_live.csv` (parsed with Python's `csv` module, not eyeballed):
```
same 9 rows → all active=False
```

This is real, current drift, not report staleness — the CSV has genuinely never been updated to match the DB flip. `brightdata-provisioning.md` even says explicitly why: the concurrent Firecrawl mission was editing the same CSV at the time, so this mission's notes went into the DB `notes` column only, with an explicit "follow-up needed: carry this into the CSV" that was never done. That follow-up is still outstanding right now.

**What I resolved beyond "is this staleness or real drift":** I read `brightdata-provisioning.md`'s own stated bar for activation — "flip `active=true`... pending real verification" of 2–3 sources returning genuine content, checked against usage. That verification is explicitly marked **not done** in the report (blocked on the zone). The zone is now provisioned (I confirmed this live — `get_active_zones` returns `web_unlocker1`), and DB shows all 9 flipped to `active=true` — but nothing in the repo shows anyone ran the verification the report's own author said was required before that flip. The one real Bright Data call on record before I intervened (`external_fetch_usage`, 1 call, 02:15 UTC) matches the hard-cap breaker's own `example.com` smoke test, not a real Downdetector fetch.

So I ran it myself: `brightdata_fetch.fetch_html()` against the live NAB Downdetector page returned a genuine 339KB page (not a block/challenge page), and the adapter's own parser read it correctly (`status='no_problems', count=4` — consistent with CE's cited NAB baseline of 3). **The activation turns out to be substantively correct** — the fetch path genuinely works for banking/government sources now. But it went live without the verification step its own build report specified, and the CSV was never synced. Good outcome, real process gap. Worth naming to the Captain directly: this is the third time in one night's chain of reports that this exact CSV/DB sync discipline slipped (CE's report notes two others) — it's a pattern, not a one-off, and worth a standing fix (e.g. `seed_source_registry.py` reads live DB state and flags drift, rather than relying on whoever last touched a CSV to remember).

---

# What CE's review didn't catch

**A. Tomorrow's Source Fidelity Audit will still be broken on its first run against tonight's new code.** Already covered above under Finding 2 — worth restating here because it's a timing point CE's report doesn't make: the bug isn't just "pre-existing and now load-bearing," it's specifically going to fire falsely-clean at 06:45 AEST tomorrow, the very first scheduled opportunity to see whether tonight's build is healthy overnight, unless the one-line fix lands before then.

**B. The Bright Data activation happened without its own stated verification gate.** Covered in detail under Finding 5. CE flagged the CSV/DB drift as a discrepancy "worth checking" but didn't have the scope to determine whether the underlying fetch path actually works for these 9 sources post-activation — I ran that check myself and can now say definitively: it works, but it was never verified before being marked live. That's a real finding CE's report stops short of, not because CE was wrong, but because CE's own report explicitly deferred it ("unverified from here").

Nothing else jumped out as missed in the areas I could check directly — CE's Findings 6, 7, and 8 (budget-exhaustion surfacing, the guard-bypass design, and the hard-cap breaker's engineering) each held up on my own spot-read of the cited code (`_maybe_push_outage_alert`, `external_fetch_budget.py`'s fail-safe-on-check-failure default) and I have no independent quarrel with them.

---

# Authority check

CE's report is Advisory-only, correctly scoped and stated as such throughout. Nothing in it self-clears any part of itself as "safe enough" or claims authority it doesn't have — the restart recommendation is framed as "do this first," not as CE having already done it, and the report is honest that its own verification (ad hoc session testing) is a different thing from confirming the scheduled job actually ran. That distinction is exactly right and is what tonight's whole incident turned on.

# Capacity check

This is a same-night, same-session follow-up gate check, not new work being proposed. Nothing here asks the Captain to do anything tonight except two cheap items: land the one-line Source Fidelity Audit fix before 06:45 AEST tomorrow if it's to be useful tomorrow, and make a call on the Downdetector cadence / report-count floor questions on their own time, not urgently. No reason to hold either of those for a fresher capacity window — both are small, bounded, and don't compound if left another day.

# Bottom line for the Captain

Restart: real, and I verified beyond what CE checked — the new paid-fetch code paths (Firecrawl/Fastly, Bright Data/NAB) both genuinely work in production right now, not just "the process is running." Field-mismatch bug: real, exact, cheap to fix, worth landing before tomorrow's 06:45 audit runs so it isn't another day of false-clean. Cadence and floor findings: real trade-offs, not urgent, worth a decision when convenient — and there's a cheaper partial fix on the cadence question (Bright Data-side headroom for banking/gov specifically) that neither report surfaces. CSV/DB drift: real, still live, and the banking/gov activation happened without its own required verification — which I've now completed myself and can confirm is genuinely working, but the process gap (third occurrence of the same CSV-sync slip tonight) is worth a standing fix, not another manual reconciliation.
