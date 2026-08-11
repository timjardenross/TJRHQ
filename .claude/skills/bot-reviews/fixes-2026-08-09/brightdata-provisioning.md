---
title: Bright Data Web Unlocker provisioning — fetch path for banking/government Downdetector AU sources
date: 2026-08-10
author: Chief Engineer (Claude Sonnet 5)
status: CODE COMPLETE, ACTIVATION BLOCKED (Bright Data account action required)
mission: Captain-directed, following on from
  downdetector-adapter-implemented.md (19 Downdetector AU sources built,
  staged inactive pending a working fetch path) and the concurrent Firecrawl
  production-provisioning work, which narrowed Firecrawl's real free-tier
  budget (1,000 scrapes/month, shared) to core telecom (Telstra/Optus/TPG/
  Vodafone/NBN) + Fastly + AEMO, and explicitly excluded the 9 banking/
  government Downdetector sources from that budget. The Captain then
  signed up for a separate Bright Data free account (5,000 requests/month —
  5x Firecrawl's) specifically to cover those 9 sources without touching
  the Firecrawl budget.
---

# Mission Summary

Provisioned and wired a Bright Data Web Unlocker fetch path for the 9
banking/government Downdetector Australia sources (NAB, ANZ, Commonwealth
Bank, Westpac, Bendigo, UBank, MyGov, Centrelink, myID) that a concurrent
mission's Firecrawl budget review excluded from the shared Firecrawl fetch
path. Code is complete, compiles clean, and a real end-to-end call against
Bright Data's live API is confirmed (correct auth, correct request shape,
real HTTPS round-trip). **Activation is blocked**: the Bright Data account
has zero Web Unlocker zones provisioned, and the supplied API key lacks the
permission to create one via the API. This needs one piece of Captain
action (below) before any of the 9 sources can go live — not fixable from
this session.

# Product selected, and why

Verified against Bright Data's own docs (docs.brightdata.com/scraping-
automation/web-unlocker), not guessed from the product name. Bright Data
offers several distinct products; only one matches "render one page, get
content back, on demand, bypassing bot detection":

| Product | Shape | Fit for this use case |
|---|---|---|
| **Web Unlocker API** | One REST call in (`POST /request` with a target URL + zone), the target site's real rendered response out. CAPTCHA-solving and anti-bot bypass (incl. Cloudflare Turnstile) handled server-side. | **Yes — used.** |
| Scraping Browser | A remote Puppeteer/Playwright session over WSS for multi-step interactive automation. | No — overkill for a single-page fetch, and this platform's adapters are plain HTTP-fetch shaped, not browser-automation shaped. |
| SERP API | Search-engine results pages only. | No — not applicable, we're fetching known company status pages, not searching. |
| Datasets | Pre-built, bulk/structured extraction (e.g. pre-scraped LinkedIn/Amazon datasets). | No — not on-demand, not this content. |

Web Unlocker's free tier is a flat **5,000 requests/month** — matches
exactly what the Captain described signing up for.

```
Endpoint : POST https://api.brightdata.com/request
Auth     : Authorization: Bearer <BRIGHTDATA_API_KEY>
Body     : {"zone": "<zone name>", "url": "<target>", "format": "raw"}
Response : the target site's raw HTML (format="raw" returns the body
           directly; format="json" would wrap it in {"status","headers",
           "body"} — raw is simpler for this codebase's regex-parsing
           adapters and matches every other fetch helper's
           string-in/string-out contract).
```

# What all 9 sources actually are (checked live, not assumed)

Re-checked `intelligence_source_registry` live via Supabase MCP before
building anything, per the brief's explicit instruction not to trust a
stale description. All 9 are confirmed:

- `source_type = 'downdetector'` for every one — **all 9 are Downdetector
  AU pages**, not a mix of source shapes. Same aria-label
  status+report-count parser (`downdetector_adapter.parse_status_and_count`)
  applies to all 9 unchanged; no new parsing logic needed.
- `active = false` for every one — **none had been reactivated by an
  alternative fetch mechanism.** The concurrent Firecrawl mission's own
  work (checked live in the same session, files still mid-edit at the time
  of checking) activated 5 "core telecom" Downdetector sources (Telstra,
  Optus, TPG, Vodafone, NBN Co) via the shared Firecrawl fetch path, and
  left 5 smaller telecom sources (iiNet, Dodo, Aussie Broadband, Superloop,
  Activ8me) and all 9 banking/government sources inactive — exactly
  matching the brief's framing. No source-specific alternative (e.g. a
  bank's own public status API) was found or substituted for any of the 9;
  Downdetector via a working fetch path is the only mechanism available for
  them.

All 9 rows' `notes` column updated live in Supabase (2026-08-10) recording
this mission's wiring + the activation blocker below, since the CSV/seed
script (`tools/intelligence/sources_live.csv`,
`tools/intelligence/seed_source_registry.py`) were being actively edited by
the concurrent Firecrawl mission at time of writing — editing the same CSV
rows concurrently risked a clobber, so that documentation currently lives
in the DB `notes` column only. **Follow-up needed:** next time
`sources_live.csv`/`seed_source_registry.py` are touched for these 9 rows,
carry the same note forward into the CSV (the canonical source of truth
per that script's own header) so a future `seed_source_registry.py` run
doesn't silently revert the DB note.

# Code built

**New module:** `intelligence/ingestion/brightdata_fetch.py` — a single
`fetch_html(url)` function, plus a `BrightDataNotConfigured` exception.

Deliberately mirrors `intelligence/ingestion/firecrawl_client.py`'s shape
(the concurrent mission's shared Firecrawl fetch module, built the same
session) for consistency — module docstring stating product choice + cost
discipline up front, a `*NotConfigured` exception, a plain `fetch_html()`
entrypoint — since that's the closest existing precedent in this codebase
for "shared fetch-path module wrapping a paid render-and-unblock API".
**Not force-fit beyond the shape**, per the brief's own instruction: Bright
Data's request/response shape genuinely differs (single `format: raw` POST
vs. Firecrawl's `formats: [...]` multi-output scrape + `success`/`data`
envelope), and Bright Data's free tier has no documented concurrency cap
the way Firecrawl's Free plan's 2-concurrent-request limit does, so
`brightdata_fetch.py` has no concurrency semaphore — Firecrawl's does,
because it needs one.

**Config additions** (`intelligence/config.py`): `BRIGHTDATA_API_KEY`,
`BRIGHTDATA_ZONE` (default `"web_unlocker1"`, Bright Data's own documented
default zone-name convention), `BRIGHTDATA_TIMEOUT_SECONDS` (default 45 —
Web Unlocker's own docs note async jobs can take up to several minutes;
this is generous headroom for a sync call well beyond the plain-fetch
15s default).

**Wiring** (`intelligence/ingestion/downdetector_adapter.py`,
`_fetch_html`): on an HTTP 403 from the plain fetch (the Cloudflare
challenge every Downdetector AU page returns), routes **by sector**:

```python
if exc.code == 403:
    sector = self._sector()
    if sector in ("banking", "government"):
        return brightdata_fetch.fetch_html(url)      # this mission's 9
    return firecrawl_client.fetch_html(url)           # telecom/other
```

This is the one piece of real design work in the wiring: the adapter's
existing 403-fallback (built by the concurrent mission) was unconditional
for the whole `downdetector` source type — if left unchanged, activating
any of these 9 banking/government sources would have silently started
spending the Captain's **Firecrawl** budget the moment they were
reactivated, defeating the entire point of provisioning a separate Bright
Data account. The sector-based branch keeps the two budgets genuinely
separate: banking/government never touches Firecrawl, telecom/other never
touches Bright Data.

# Credential handling

`BRIGHTDATA_API_KEY` and `BRIGHTDATA_ZONE` stored in both:
- `/opt/starship-endeavour/platform-runtime/.env` — the file
  `intelligence-scheduler.service` actually loads via systemd's
  `EnvironmentFile=` (confirmed by reading the live unit file — this is
  the real production credential path, not an assumption).
- `/opt/starship-endeavour/.env` (repo root) — `intelligence/config.py`
  also does its own `load_dotenv(REPO_ROOT / ".env")` independently of
  systemd, so this covers any manual/ad hoc invocation of the pipeline
  outside the systemd unit.

Both files were already `chmod 600` and already covered by `.gitignore`
(`.env` / `.env.*` patterns, both at repo root and in
`platform-runtime/.gitignore`) — verified with `git check-ignore -v`
*before* writing the key to either file, per the brief's explicit
instruction. `git status` confirms neither file appears as trackable after
the edit. The key value itself never appears in this document, in any
commit, or in any tool output produced during this session — referred to
throughout only as "the Bright Data key" / `BRIGHTDATA_API_KEY`.

# Verification performed

- `python3 -m py_compile` clean on all touched/new files, run via the
  actual production venv (`platform-runtime/.venv/bin/python`) to match
  how `intelligence-scheduler.service` really runs this code.
- **Real end-to-end call confirmed reaching Bright Data's live API**, run
  via `platform-runtime/.venv/bin/python` importing `brightdata_fetch`
  directly (not mocked, not curl standing in for the module — the actual
  production code path): the call correctly authenticates, correctly
  builds the request, and gets back a real, documented Bright Data
  response:
  ```
  Bright Data Web Unlocker HTTP 400 for
  https://downdetector.com.au/status/national-australia-bank/:
  zone "web_unlocker1" not found
  ```
  This proves the credential is valid, the module is hitting Bright Data's
  real API (not silently failing or falling back to anything else), and
  the request shape is correct — the ONLY thing missing is the zone itself.
- **Could not complete the brief's full verification ask** (2-3 real
  test-fetches returning genuine page content, checked against Bright
  Data's dashboard/API for real usage) — blocked by the issue below before
  any successful fetch is possible.

# Blocker: no Web Unlocker zone provisioned, and the key can't create one

Confirmed via Bright Data's own account-management API
(`GET https://api.brightdata.com/zone/get_active_zones`) that this account
currently has **zero active zones** — `[]`. Bright Data's Web Unlocker
product is not auto-provisioned on signup; a zone must exist before
`POST /request` will do anything (confirmed against
docs.brightdata.com/scraping-automation/web-unlocker/quickstart).

Attempted to create one programmatically (`POST /zone`, the documented
"Add a Zone" endpoint, `{"zone": {"name": "web_unlocker1", "type":
"unblocker"}, "plan": {"type": "unblocker", "country": "au"}}`) — rejected
consistently, on repeated attempts with varied payloads, with:

```
Your API key lacks the required permissions for this action.
You can change your token permissions at https://brightdata.com/cp/setting/users
```

This is a real, specific, actionable permissions message (not a payload
error — the same key successfully authenticates against read-only
endpoints like `get_active_zones`). Bright Data scopes API keys by
permission level (Admin/Finance/Ops/Limit/User); zone management requires
Admin or Ops. The key provided to this session does not have that scope.

**This cannot be resolved from this session** — it requires one of two
Captain actions on the Bright Data account itself, whichever is faster:

1. **Create the zone manually** in the Bright Data Control Panel: Web
   Access APIs → Create API → Web Unlocker API → name it `web_unlocker1`
   (matching this codebase's `BRIGHTDATA_ZONE` default — or pick any name
   and set `BRIGHTDATA_ZONE` in `platform-runtime/.env` and `.env` to
   match). A few clicks, no code change needed afterward.
2. **Grant the existing key Admin/Ops permission** at
   brightdata.com/cp/setting/users, then this session (or a follow-up one)
   can create the zone via the API call already written and tested above.

Once either happens, no further code changes are needed — re-run the
verification call
(`platform-runtime/.venv/bin/python -c "from intelligence.ingestion import
brightdata_fetch; print(brightdata_fetch.fetch_html('https://downdetector.
com.au/status/national-australia-bank/')[:200])"`) and it should return
real HTML immediately.

# What's NOT done, and why

**None of the 9 sources were activated** (`active` left `false` in
`intelligence_source_registry`). The brief's own verification bar — real
test-fetches of 2-3 sources confirmed returning genuine content, checked
against Bright Data's usage dashboard — could not be met given the zone
blocker above, and activating sources whose fetch path is confirmed
non-functional would misrepresent them as live, exactly the mistake the
companion Downdetector mission's own report flagged and avoided for the
same 9 sources' predecessor state. This follows that same established,
correct precedent in this codebase: build and wire fully, verify what can
genuinely be verified, disclose the blocker, stay inactive until real
content is confirmed.

# Mission Status

Code complete and correct (compiles clean, real API connectivity proven).
Blocked on a Bright Data account action outside this session's authority —
see "Blocker" above for the exact two options. Once unblocked: re-run the
verification call above for 2-3 sources, confirm genuine Downdetector
content (not a block/challenge page) comes back, then flip `active=true`
for the 9 rows in `intelligence_source_registry` (SQL already drafted,
not yet run — intentionally, pending real verification).
