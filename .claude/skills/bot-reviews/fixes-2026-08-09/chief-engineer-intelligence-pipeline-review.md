---
title: Chief Engineer whole-architecture review — intelligence-gathering pipeline (outage detection chain)
date: 2026-08-10
author: Chief Engineer, USS-TJR-003, Engineering Division — Advisory only
scope: Every report in .claude/skills/bot-reviews/fixes-2026-08-09/ touching the outage
  detection/alerting chain, reviewed as one interacting system, plus direct verification
  against the live production code, the live running systemd service, and live Supabase
  data (project cjvrpjwewsrumnbdydgg). NOT a re-litigation of any individual mission's
  own scoping decisions.
status: Advisory. One finding (#1) is time-sensitive and actionable within minutes.
---

# Mission Summary

Tonight's session built a genuinely substantial outage-detection pipeline: a
Cloudflare/Akamai/GCP/GitHub/etc. impact-field noise filter, a five-guard
outage push-alert trigger (event type → customer impact → confidence →
outage-language check → vendor-tier allowlist → LLM blast-radius check), a
new Downdetector Australia crowdsourced-report-volume adapter with its own
two-layer gate, Firecrawl and Bright Data fetch-path capabilities to get
past Cloudflare/WAF blocks, a DB-backed hard-cap circuit breaker for both
paid providers, and durable audit logging for the whole thing. Read in
isolation, each mission's own report is honest, well-verified against real
data, and mostly correct about what it built. This review asked: now that
all of it exists and interacts, what does the whole system actually do —
and is that what the reports say it does?

The single most important finding is that **most of tonight's outage-pipeline
code is not currently running in production**, for a reason no individual
mission's own verification could have caught (each one verified its own code
by calling it directly in an ad hoc session, never by confirming the actual
scheduled job produced the expected result). Everything else in this review
is real but secondary to that.

# Findings, ranked by real severity

## 1. [CRITICAL, time-sensitive] Nearly all of tonight's outage-pipeline code is sitting in git, not running in production

**Verified directly against the live host**, not inferred from a report:

```
$ systemctl show intelligence-scheduler.service -p ActiveEnterTimestamp
ActiveEnterTimestamp=Mon 2026-08-10 09:09:38 AEST
```

The live `intelligence-scheduler.service` process (PID 1215086, the single
owner of all scheduled collection/brief/alert jobs per its own unit-file
docstring) has been running continuously since **09:09:38 AEST**. It is a
long-running `Type=simple` daemon with `Restart=always` — it restarts on
crash, but nothing restarts it when new code is committed. There is no
deploy hook, no git hook, no systemd path unit, no CI/CD step anywhere in
this repo that restarts it after a push — confirmed by checking
`.git/hooks/` (empty except samples), `systemctl list-units --type=path`
(nothing matching), and the `deploy/` directory (service/timer unit files
only, no restart automation).

`git log` shows the following landed **after** that restart, all still on
`origin/main`, none of it live:

| Commit | Time (AEST) | What |
|---|---|---|
| `2abf9674` | 09:50 | Vendor-tier allowlist guard (guard 5) |
| `77132066` | 09:58 | LLM blast-radius guard (guard 6) |
| `181780c1` / `0d797043` | 10:02–10:03 | Akamai + 5 Statuspage migrations + GCP parser |
| `e86a6183` … `c8e19827` | 10:51 | Downdetector adapter built + registered + 19 sources added + guard-bypass wired |
| `fb6a8ac8` | 11:20 | Bright Data fetch path |
| `1497beb3` | 11:30 | ScrapeAdapter Firecrawl-fallback allowlist + nav-chrome fix |
| `4b928399` | 12:17 | Hard-cap circuit breaker (the enforcement mechanism itself) |

That is: guards 5 and 6 of the outage push-alert pipeline, the entire
Downdetector adapter and its 14 currently-`active=true` sources, the
Fastly/AEMO Firecrawl fallback, and the hard-cap circuit breaker that the
Captain explicitly asked for as a *real, enforced* stop — none of it has
executed in production even once.

This is not a theoretical staleness risk — it's directly visible in the
live health data, which shows the **exact pre-fix failure signatures**:

```sql
-- most recent health row per source, live, 2026-08-10
Fastly Status            | failed  | "HTTP 403 from https://www.fastlystatus.com/incidents"
AEMO Market Notices      | failed  | "HTTP 403 from https://www.aemo.com.au/market-notices"
Downdetector AU — *  (all 19) | skipped | "Manual source type — no programmatic collection"
```

The current repo code has `"downdetector": DowndetectorAdapter` correctly
registered in `intelligence/ingestion/collection_engine.py`'s `_ADAPTER_MAP`
(verified by reading the file), and `"Fastly Status"` correctly on
`scrape_adapter.py`'s `_FIRECRAWL_FALLBACK_SOURCE_NAMES` allowlist. The
"skipped / Manual source type" and plain "HTTP 403 / no fallback" messages
are *only* producible by code that predates those changes — i.e. exactly
what a process running since 09:09:38 would produce. This is a live,
reproducible, checkable fact, not speculation about deploy process.

Corroborating evidence: `external_fetch_usage` (the hard-cap ledger every
real Firecrawl/Bright Data call increments) shows **exactly one call ever
recorded for each provider**, both timestamped 02:15 UTC (12:15 AEST) —
matching precisely the one manual `scrape('https://example.com')` /
`fetch_html('https://example.com')` smoke test each provisioning mission ran
against its own ad hoc session, not a real Downdetector/AEMO/Fastly fetch.
**Zero real production calls to either paid provider have ever happened.**

**Consequence, concretely:** right now, in production, a single-vendor
status-page blip from Notion/DocuSign/Canva/Zoom/GitHub/etc. with
`customer_impact=high` and `confidence>=0.65` and any outage-language
keyword **will still push to Telegram** — the exact false-positive class
`outage-scale-gate-implemented.md` and `outage-scope-llm-check-implemented.md`
each verified fixed, in a process that isn't the one actually running. The
base 4-guard push-alert (`event_type`/`customer_impact`/`confidence`/
`_has_outage_language`, landed the previous evening in `b6fb178d`, before
the restart) *is* live; everything built on top of it tonight is not.

**Recommendation — do this first, before anything else in this review:**
`systemctl restart intelligence-scheduler.service`. Every piece of code
involved has already been unit-verified and, in most cases, run end-to-end
against live data in an ad hoc session — this is a low-risk restart of
already-tested code, not new work. After restarting, re-check the next
`intraday_status_collection` and `daily_source_collection` health rows to
confirm Downdetector/Fastly/AEMO actually go from `skipped`/`failed` to
`ok`/expected-empty, and confirm at least one real (non-`example.com`)
`external_fetch_usage` increment appears for each provider.

**Systemic point, not just tonight's incident:** this repo has no
restart-after-deploy discipline for its long-running daemons. On a night
with 60+ commits landing across many concurrent sessions, "the code is
merged" and "the code is running" silently diverged for hours, and nothing
in the pipeline would have caught it except a live health-data check like
this one. Worth a standing convention (documented in the unit file's own
header, or a lightweight post-push check) rather than relying on the next
person to think to check `ActiveEnterTimestamp` against `git log`.

## 2. [HIGH] The one mechanism meant to catch exactly this kind of silent failure is itself silently broken

`intelligence/scheduler.py::_source_fidelity_audit_job()` (runs daily 06:45
AEST) reads:

```python
report = source_fidelity_report(days=30)
high_value = len(report.get("high_value_sources", []))
low_value = len(report.get("low_value_sources", []))
degraded = len(report.get("degraded_sources", []))
```

But `intelligence/audit/source_fidelity.py::source_fidelity_report()`
returns those three keys **nested under `report["summary"]`**
(`report["summary"]["high_value_sources"]` etc.), never at the top level.
`report.get("high_value_sources", [])` therefore always falls through to
the default `[]` — `high=0 low=0 degraded=0` is written to the heartbeat
**every single day, regardless of real data**, and the job still logs
`status="ok"`. This is a pre-existing bug (the file dates to 2026-07-30,
untouched tonight), not something tonight's session introduced — but
tonight's session made it load-bearing: `downdetector-adapter-implemented.md`
and `firecrawl-production-provisioning.md` both explicitly point to "the
Source Fidelity Audit / Workbench" as the visibility mechanism for a fetch
failure. It always reports clean. A monitor that always says zero degraded
sources is worse than no monitor, because it actively signals health that
isn't being measured. Cheap fix: read `report["summary"][...]` in
`scheduler.py`, or flatten the keys in `source_fidelity_report()`'s return —
either works, this is a one-line fix once someone looks at it directly.

## 3. [HIGH] Downdetector's cadence works against its own reason for existing

Confirmed in `intelligence/scheduler.py`: `_excluding_firecrawl_fetch_sources()`
explicitly filters `source_type != "downdetector"` out of the 180-minute
`_intraday_status_collection_job` (budget discipline — correct and
deliberate, see `firecrawl-production-provisioning.md`'s cost math). The
practical effect: Downdetector sources are polled **once a day** at 06:00,
the same cadence as the slowest tier in the pipeline, while the vendor
self-report sources it was built to complement (Cloudflare, AWS, GitHub,
Azure, GCP, Salesforce, etc.) are polled **~8x/day** via the intraday job.

Downdetector's own module docstring and the design report both frame it as
"faster crowdsourced signal" than daily vendor status pages. In actual
deployed cadence, it is the *slowest* active signal in the outage-detection
pipeline, not the fastest. A genuine fast-moving outage that spikes and is
substantially resolved within a single day (plausible for a bank app outage
or a mobile network issue — Telstra's own real July outage lasted under two
days) has a real chance of falling entirely between two 06:00 checks,
missing the report-volume peak Downdetector exists to catch. This is a
disclosed trade-off in the reports (budget-driven, not an oversight), but
its consequence — the newest, most-hyped signal is also the one with the
weakest temporal resolution — is not stated plainly anywhere in the chain of
reports, and is worth the Captain knowing explicitly rather than inferring
from scattered cost-math paragraphs.

## 4. [MEDIUM-HIGH] One report-count floor, one historical data point, three structurally different sectors, and zero downstream backup

`_REPORT_COUNT_FLOOR = 150` in `downdetector_adapter.py` is a single global
constant applied identically to telecom, banking, and government sources.
It was derived from exactly one real historical event (Telstra's July 2026
outage: 230–354 peak reports vs. a 1–42 quiet baseline). The adapter's own
live quiet-day sample (2026-08-10, all 19 companies) shows banking and
government baselines are **5–10x lower in absolute terms** than telecom's:
NAB 3, ANZ 3, Westpac 3, UBank 2, Centrelink 2, myID 1 — vs. Telstra 34, TPG
7. If a genuine bank-app outage produced the *same relative* spike Telstra's
did (6–10x baseline), a bank sitting at a baseline of 3–7 would peak around
20–70 reports — nowhere near the shared 150 floor calibrated against
telecom's much larger absolute baseline. The floor may simply be too high
for banking/government to ever fire, even for a real, proportionally severe
event.

This risk is compounded by a design choice that is otherwise correct (see
Finding 7): Downdetector-sourced events deliberately **skip both downstream
guards** (vendor-tier allowlist, LLM blast-radius check) that protect every
other source in the pipeline. That bypass is the right call — but its
consequence is that this one uncalibrated, one-data-point constant is now
the *entire* line of defense for the banking/government sources, where
every other source type in the pipeline got two to three additional layers
of protection built for it tonight. The reports disclose the floor is a
"first-cut, not yet proven" number needing calibration — they do not
connect that disclosure to the fact that, for this source, there is nothing
else standing behind it. Recommend flagging banking/government Downdetector
sources for a lower, sector-specific floor (or at minimum active monitoring
of real report-count distributions once live) rather than treating this as
generically "needs a few weeks of calibration" — the risk profile is
different by sector, not just less-proven overall.

## 5. [MEDIUM] The classifier's bare-keyword weakness (MSN-0361) is real, unfixed, and now has visible scaffolding built entirely around one narrow use of it

Confirmed directly in `intelligence/classification/classifier.py`:
`technology_outage`'s keyword list includes bare, generic terms — `"aws"`,
`"azure"`, `"google cloud"`, `"microsoft"`, `"cloud"`, `"platform"`,
`"salesforce"`, `"servicenow"` — that fire on any story mentioning a tech
vendor, not just outage reports. `xo-review-followups.md` confirmed live:
152/510 (30%) of all `technology_outage`-tagged events over 30 days rely
*solely* on these generic terms with no genuine incident language.

Tonight's response was a defensible, narrow, well-reasoned decision: fix it
at the push-alert trigger only (`_has_outage_language`), not at the
classifier, because the classifier is a shared module feeding every other
consumer. That's the right call for a same-night fix. But the honest
follow-through is worth stating plainly rather than leaving implicit: five
to six guards were built tonight, layered specifically to compensate for
this one field's unreliability, and every one of them protects **only the
outage push-alert path**. The same `event_type`/`customer_impact` fields,
with the same 30% bare-keyword contamination rate, still flow unguarded
into:
- the weekly OSINT roll-up counts (`🔴 16 high · 🟡 9 medium · 🟢 211 low`),
- `banking_relevance`/`cps230_relevance` flags used elsewhere in this
  platform's CPS230 framing,
- `intelligence/content_intelligence_service.py`'s content-angle suggestion
  pipeline (the literal origin of the 4-week-stale "Telstra outage... stark
  reminder" draft that helped prompt tonight's whole investigation).

None of tonight's work made the classifier itself more trustworthy — it
made one specific, narrow consumer of it trustworthy by building enough
compensating machinery around it. That's a legitimate scoping decision, not
a criticism of the individual missions, but it means the platform-wide risk
this review was asked to assess is unchanged: still open, still real, and
now slightly more expensive to eventually fix properly, because more
callers implicitly depend on its current behavior (the push-alert guards
were tuned against the classifier's *current* false-positive shape; fixing
the classifier later could shift what those guards need to catch).
Recommend the already-flagged dedicated `technology_outage`/`telecom_outage`
keyword-tightening pass (same treatment as the four other categories fixed
2026-07-18) get scheduled as real, scoped work rather than staying
indefinitely deferred.

## 6. [MEDIUM] Budget-exhaustion handling is well-built at the code level; its surfacing story is effectively silent

Verified by reading `firecrawl_client.scrape()`, `brightdata_fetch.fetch_html()`,
`external_fetch_budget.check_and_increment()`, `downdetector_adapter._fetch_html()`,
`scrape_adapter._fetch_html()`, and `base_adapter.run()` together as one
chain: a `FetchBudgetExceeded`/`FetchBudgetCheckFailed` raised by the budget
gate is **not** caught locally by either fetch client or either calling
adapter — it propagates cleanly up to `base_adapter.run()`, which records
`SourceHealth(status="failed", error_message=...)`. This is the right
behavior and directly answers the question this review was asked to check:
a budget-refused fetch does **not** silently degrade into "no problems
detected" (that would require `collect()` to catch the exception and return
`[]`, which none of these adapters do). A failed fetch is recorded as
failed, not as a clean quiet check. This part of the design is genuinely
correct, not just claimed correct.

The gap is what happens to that "failed" record afterward: it lands in
`intelligence_source_health`, feeds the broken counter in Finding 2, and the
one tool that reads current usage proactively
(`tools/external_fetch_usage_check.py`) is a plain CLI script — confirmed
not wired into `scheduler.py`, `captains_brief.py`, or
`infra_narrative.py` anywhere. So: fails loud in the log, fails silent to
the Captain. `external-fetch-hard-cap.md`'s own report discloses this
("no alerting/notification fires... a human needs to either watch logs or
run the tool") — confirmed true, not overstated. Recommend wiring
`current_usage()` into the existing Platform Health infra-narrative path
(same pattern `verification_state`/`degraded_domains` already uses) so
"Firecrawl at 92% of ceiling" becomes visible the same way other platform
degradation already is, rather than adding a fourth parallel
visibility mechanism.

## 7. [Positive — verified, not just claimed] The Downdetector guard-bypass design is correct, and actually implemented as documented

This was the first thing this review set out to check skeptically: does
Downdetector-sourced events really skip the vendor-tier/blast-radius guards,
and is that the right call? Read `intelligence/persistence/intelligence_store.py`
directly (not the report's description of it): `_maybe_push_outage_alert()`
branches on `_is_downdetector_source(event)` (a source-name prefix match)
and, when true, explicitly skips both `_passes_vendor_tier_gate()` and
`_passes_blast_radius_check()`, with the reasoning inline in a dated
comment. Verified true, not just claimed.

The reasoning holds up under scrutiny: the vendor-tier allowlist
(`_FOUNDATIONAL_INFRA_VENDORS`) would suppress every genuine
Downdetector-confirmed outage for any company not on that 8-name list —
Vodafone, every minor ISP, all four major banks, MyGov/Centrelink/myID —
which is most of what this source exists to cover. The blast-radius LLM
prompt's own definition of "narrow" ("confined to one vendor's own service
... even if that vendor is itself a large hyperscaler or carrier") would
plausibly and wrongly classify a real, materially significant single-bank
outage as narrow. Both are real, correctly-identified failure modes of
reapplying vendor-self-report heuristics to a differently-shaped signal —
this is good architectural judgment, genuinely followed through in the
code, not just asserted in a doc. (Finding 4 above is a separate concern —
not whether the bypass is right, but what stands behind it once the bypass
is applied.)

## 8. [Positive] The hard-cap circuit breaker is solid engineering

Row-locked atomic Postgres RPC, a genuine bug caught by the mission's own
live testing before merge (`RETURN QUERY` not exiting a PL/pgSQL function,
letting the counter climb past a refused call), fail-safe-not-fail-open on
check failure (explicitly the opposite default from `llm_cost_governance.py`,
with the difference reasoned rather than accidental), and provider-specific
non-calendar billing-cycle anchoring, all verified present in
`external_fetch_budget.py`. This is real defense against exactly the "cron
misconfiguration quietly blows through a personal API budget" scenario it
was built for — once it's actually running (Finding 1).

# Recommendations, in order

1. **Now:** `systemctl restart intelligence-scheduler.service`, then verify
   the next collection cycle's health rows for Fastly/AEMO/Downdetector show
   real behavior, not the pre-fix signatures documented in Finding 1.
2. **Cheap, do soon:** fix `_source_fidelity_audit_job()`'s key mismatch
   (Finding 2) — one-line change, closes a false-clean monitor.
3. **Needs a decision, not urgent tonight:** either accept Downdetector's
   once-daily cadence as a disclosed trade-off (Finding 3) or reconsider
   whether the 5 core-telecom sources specifically warrant intraday polling
   within the existing Firecrawl budget headroom (≈224/month used of 850
   ceiling per `firecrawl-production-provisioning.md`'s own math — there is
   real room, though intraday would multiply usage ~8x for whichever sources
   are included).
4. **Before activating the 9 banking/government Downdetector sources for
   real** (they show `active=true` live right now, per Finding 4's
   discovery — see also the registry-drift note below): reconsider the
   150-report floor per sector rather than reusing the telecom-derived
   number as-is.
5. **Scoped follow-up, not tonight:** the `technology_outage`/
   `telecom_outage` classifier keyword tightening (Finding 5), same
   treatment already applied to four other categories 2026-07-18.
6. **Low effort:** wire `external_fetch_budget.current_usage()` into the
   existing Platform Health narrative path (Finding 6).

# One more live discrepancy worth flagging directly to the Captain

`brightdata-provisioning.md` (last report in that chain) states explicitly
that none of the 9 banking/government Downdetector sources were activated,
pending the Bright Data zone-provisioning blocker. **Live Supabase data
checked during this review shows all 9 are currently `active=true`** in
`intelligence_source_registry`, while `tools/intelligence/sources_live.csv`
(this platform's own documented source of truth) still shows all 9 as
inactive — the exact CSV/DB drift pattern flagged as a recurring problem by
three separate reports tonight, recurring again, this time on sources whose
fetch path was last confirmed non-functional. Whether the Bright Data zone
blocker was subsequently resolved by someone outside this session is
unverified from here — but the activation happened without the
verification-then-CSV-sync discipline every other change tonight followed,
and (per Finding 1) none of it is executing yet regardless. Worth a direct
check before or immediately after the recommended restart, not left to
surface on its own.

# Mission Status

Advisory only. Finding 1 is the load-bearing one — it doesn't invalidate
any individual mission's engineering, all of which checks out as reported
when read against the actual committed code, but it means the Captain's
mental model of "this is live and enforcing" does not currently match
production reality for most of tonight's work. Recommend the restart in
Finding 1 happen before further outage-pipeline work is commissioned on top
of what's already built.
