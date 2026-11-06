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

## Lesson

See LL-201 and LL-202 in `knowledge/Lessons-Learned.md`.

## Future Guidance

- Any new alert adapter must: return its skips through the ledger with a reason, declare `stale_after_hours` and `expected_fields` in `SOURCE_INFO`, and ship a fixture captured from the real feed. The register and drift tests fail otherwise.
- Do not apply 0252 or flip any heartbeat `critical` flag without the Captain's explicit go-ahead.
- Held by the Captain: NT and ACT warnings work. Not done: backfill of expired ACT/VIC/TAS timezone rows and 15 DST-affected BOM rows; myID is unmonitored.
