# Knowledge Record — Emergency Alert Hub ingestion integrity uplift, 2026-11-06

| Field | Value |
|---|---|
| Mission ID | EAH-INGESTION-INTEGRITY-UPLIFT |
| Title | "No alerts" only means quiet if the pipeline can prove it is not broken: every skipped item is now counted, every feed is checked for going quiet or changing shape, and the counts are queryable |
| Date | 2026-11-06 |
| Lesson | LL-201, LL-202 |

## Outcome

Delivered in PRs #587-#591 and the persistence follow-up (migrations 0250, 0251 applied; 0252 authored, applied only on the Captain's go-ahead).

- **Drop accounting.** `DropLedger` (`intelligence/ingestion/emergency_alert_adapters/base.py`) counts `items_seen` and every excluded / invalid / unmapped item with a reason, plus up to three public example titles per reason, and the newest source-side item time. Invariant, tested on every fixture: `items_seen == accepted + excluded + invalid`.
- **Per-row isolation.** One malformed item is counted as `invalid_*` and skipped; it no longer fails the whole source. An all-invalid run fails the integrity gate (no expiry, failed heartbeat).
- **Data-quality checks (never fail a source, warn in the heartbeat):** `STALE` (newest item older than the feed's own `stale_after_hours`) and `FIELD DRIFT` (an `expected_fields` field missing on every alert of a run of 3+). Both are declared per source in `SOURCE_INFO`.
- **Mapping register** `docs/emergency-alerts/mapping-register.md` is generated from `SOURCE_INFO` (`scripts/emergency_alerts/build_mapping_register.py --check` in CI), so the documentation cannot drift from the code.
- **Real snapshot tests** against committed fixtures captured from the live feeds (`tests/fixtures/emergency_alerts/`, `scripts/emergency_alerts/dump_fetch_outputs.py`).
- **Timezones measured, not assumed.** ACT and VIC incident times are local time that had been stored as UTC (about +11 h); TAS ArcGIS epochs are Hobart wall-clock-as-UTC; NSW is genuinely UTC. Fixed forward (`_localize`); expired historic rows not backfilled. SA `updated_at_src` was NULL on every row (`<sent>` is a child of `<alert>`, not `<info>`) and is fixed.
- **Persistence and surfaces.** `emergency_alert_source_integrity` (one row per source, upserted once per run, best effort and never fatal), a "what the hub is dropping" section in the daily digest, and in the portal: CAP fields in the alert detail, an integrity list in the Coverage panel, and a `stale_content` coverage gap.
- **Retired:** AEMO NEMweb and myID sources (inactive in the registry).

## What was measured and found, not fixed

- A failed emergency heartbeat does not page in real time. It lands in `domain_heartbeat_latest` and the morning brief only lists `critical` domains; every `emergency_alert_*` domain has `critical = false`. Recommendation: set them critical, or add a feed-down email. Awaiting the Captain's decision.
- Healthy heartbeats are throttled to one per 20 minutes; failed ones are always written. Staleness threshold for emergency sources is 45 minutes. Consistent, no change needed.
- CAP-AU: the NSW RFS CAP feed is a superset of the GeoJSON feed; VicEmergency's CAP feed is not public; SA CFS already publishes CAP. A NSW CAP adapter needs approval.
- The live-feed canary was delivered as an in-run `FIELD DRIFT` check rather than a separate scheduled job: same signal, no extra moving part.

## Addendum 2026-11-06: CAP enrichment (NSW RFS, BoM)

- **NSW RFS:** `nsw_rfs_cap.py` copies CAP event / urgency / certainty / severity onto the GeoJSON alerts by RFS incident id (an enrichment, not a second source; an outage raises FIELD DRIFT).
- **BoM:** `bom_cap.py` does the same for the eight `bom_*` feeds from the WMO mirror of BoM's CAP-AU stream. The BoM RSS items and bulletin pages carry no product code, so the match is conservative (warning type plus location words, or a unique same-state message sent within 90 s) and an ambiguous match is left unenriched; 18 of 24 non-marine items matched when measured, none wrongly. BoM CAP severity is never used for our tier. Personal use only; `EMERGENCY_ALERTS_BOM_CAP=0` switches it off.
- **Measured conformance (real XSDs, kept in `tests/fixtures/cap_schemas/`):** against OASIS CAP 1.2, 120/120 sampled BoM messages and 8/8 NSW messages are valid. Against the CAP-AU v3.0 XSD (fetched from bom.gov.au), NSW 8/8 and SA 7/7 are valid and BoM is 115/120 (the 5 failures are Bushwalkers Weather Alerts whose `<event>` 'Exposure' is outside the CAP-AU event list). The QLD storm / flood / cyclone feed fails both: its `<sent>` / `<expires>` read `...+00:00+10:00`, and `expires` is a year ahead. `tests/test_cap_schema_conformance.py` validates the fixtures (skipped without lxml).
- **Not done:** QLD CAP enrichment (needs a tolerant timestamp parser and cannot be used for expiry); WA, ACT and TAS have no confirmed CAP feed; BoM geography (area codes only, no polygons).

## Addendum 2026-11-06 (later): backfill and paging

- **Timezone backfill (run, with backup).** Expired rows kept the old wrong times after #591: 3,485 VIC incident rows, 527 ACT rows and 1 TAS row were corrected by reading the stored digits as local time and converting (zone database, per-row date). Before: 3,477 of the VIC rows claimed to be issued after we last saw them; after: 0, average issued-minus-first-seen -0.31 h. 15 BOM rows whose "Issued at" line had no timezone (NSW/ACT/VIC/SA/TAS) were filled in from that line; each lands 0-1 minute before its RSS pubDate. All 4,028 changed rows are in `alerts_tz_backfill_backup_20261106` (drop it once accepted). Record and reversal: `scripts/emergency_alerts/backfill_timezones_20261106.sql`. The adapter now reads those no-timezone lines with the state's zone, so new rows are no longer left NULL.
- **Not recoverable:** SA `updated_at_src` is still NULL on every row written before #591 (the `<sent>` value was never read, so nothing stored to derive it from), and 18 BOM rows with no "Issued at" line (cyclone advices, flood watches) have no issue time to derive.
- **Failed-heartbeat paging.** All 17 `emergency_alert_*` domains are now `critical = true` (migration 0253), so a stale or failing collector appears in the morning-brief Platform Health card. `critical` does NOT page in real time; a feed-down email would be a separate change.

## Addendum 2026-11-06 (latest): email alert changes

All defaults leave existing behaviour unchanged except the additions to the header and LIFTED body.

- **[FEED] emails** (`_send_feed_emails`): a source that fails 3 runs in a row (~45 min), or whose feed goes STALE, emails once, repeats every 12 h while down, and emails once when it recovers. State lives in `emergency_alert_feed_state` (migration 0254, **authored, not applied**); until it is applied nothing is sent and a warning is logged.
- **Advice emails (opt-in):** `EMERGENCY_ALERT_ADVICE_EMAIL="NSW:flood,*:bushfire,QLD:*"` switches `[ADVICE]` emails on for those jurisdiction:hazard pairs. Unset (default) = off. Silenceable. Advice gets no wording-update or LIFTED follow-ups (only an escalation emails), and is closed out silently.
- **Per-tag recipients:** `EMERGENCY_ALERT_EMAIL_TO_<TAG>` / `EMERGENCY_ALERT_EMAIL_CC_<TAG>` (TAG = EW, WA, BOM_HIGH, ADVICE, UPDATE, LIFTED, FEED) override the default recipients for that kind of email only.
- **Header:** `CAP-Event`, `CAP-Urgency`, `CAP-Certainty`, `CAP-Severity` (when the source has them, as given), `Issued-Local` and `Sent-At-Local` (the jurisdiction's own clock, e.g. `2026-11-06 20:00 AEDT`). Appended after the existing keys; existing key order is unchanged. Queensland uses a fixed AEST offset because the repo's timezone guard bans naming the Brisbane zone.
- **LIFTED:** says how long the source listed the alert (`Listed-For: 3h 20m`).
- **Daily digest:** always opens its feed-health section with a pipeline check ("16 of 16 sources reported in the last 2 hours; saw N items, kept M"), and warns when sources have not reported.

## Addendum 2026-11-06 (holistic review follow-ups)

- **NSW coordinates:** about 81% of stored NSW rows had no latitude/longitude because only a Point inside a GeometryCollection was read; a bare Point (most features) is now read too (PR #598).
- **BoM heatwave:** `Heatwave Warning (NT/QLD/WA)` were dropped as an unmatched product; they are now ingested as `heatwave` (Captain-approved; WA already did). BoM does not state a level in the title, so they stay severity unknown at standard attention (no BOM-HIGH email).
- **QLD identity:** the QLD feed gives each re-issue of a warning a new UniqueID, so one fire (Teelah, 21-25 Sep) made 12 rows, and a live email each. `event_key` is now the warning area plus the local date, with two same-area same-day warnings collapsed to the highest tier (`excluded_superseded`), and the QLD content hash ignores the "as at <time>" part of the title (hash version `h3:`; a changed recipe is baselined silently). One-off effects at deploy: any currently active QLD Watch and Act / Emergency Warning gets one new row and so one repeat email, and a fire that crosses local midnight gets one new row at the date change.
- **WA enrichment:** the DFES JSON API (`/v1/warnings`, `/v1/incidents`) shares ids with the RSS guids, so `wa_json.py` fills `issued_at` (the RSS has none), the CAP urgency/certainty/severity/event for warnings, and incident status (Active / Monitoring / On scene) plus street and suburbs. Only empty fields are filled; an outage keeps RSS-only alerts and raises FIELD DRIFT (`issued_at`).
- **VIC:** incident rows already carry status, agency and size in the description; their tier is unknown because the VIC incident feed has no warning level.
- **SA backfill:** `updated_at_src` filled for 87 of the 541 NULL rows from the timestamp in their `event_key` (backed up); the other 454 keys carry no time and stay NULL.

## Lesson

See LL-201 and LL-202 in `knowledge/Lessons-Learned.md`.

## Future Guidance

- Any new alert adapter must: return its skips through the ledger with a reason, declare `stale_after_hours` and `expected_fields` in `SOURCE_INFO`, and ship a fixture captured from the real feed. The register and drift tests fail otherwise.
- Do not apply 0252 or flip any heartbeat `critical` flag without the Captain's explicit go-ahead.
- Held by the Captain: NT and ACT warnings work. Not done: backfill of expired ACT/VIC/TAS timezone rows and 15 DST-affected BOM rows; myID is unmonitored.
