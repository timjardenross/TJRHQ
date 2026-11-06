# Emergency Alert Hub - mapping register

> GENERATED FILE - do not edit. Source: the `SOURCE_INFO` dict in each adapter under
> `intelligence/ingestion/emergency_alert_adapters/`. Regenerate with:
>
> `python scripts/emergency_alerts/build_mapping_register.py`

Every mapping assumption the hub makes about an official feed, in one place: where severity
comes from, how it maps, what is deliberately dropped (and who decided), and what the feed
cannot tell us. A test fails if this file is stale.

Drop-ledger reasons: `excluded_<reason>` = deliberate, Captain-directed filter (quiet, not broken);
`invalid_<reason>` = structural failure (broken); `invalid_unparseable_item` = any item that could not
be parsed at all (applies to every source); `unmapped_<label>` = a kept alert whose tier label is not
recognised (severity `unknown`).

## Summary

| Source | Severity source | Exclusions | Known gaps | Last verified |
| --- | --- | --- | --- | --- |
| `act_esa` | none - the ESA incident feed carries no warning level | 2 | 2 | 2026-08-26 |
| `bom_*` | none - the BOM feed carries no AWS tier (always 'unknown') | 3 | 6 | 2026-08-27 |
| `nsw_rfs` | properties.category (Advice / Watch and Act / Emergency Warning) | 2 | 3 | 2026-08-26 |
| `nt_securent` | none - NT fire/emergency alerts are not monitored | 0 | 2 | 2026-11-01 |
| `qld_fire` | properties.WarningLevel (Advice / Watch and Act / Emergency Warning) | 2 | 2 | 2026-08-26 |
| `sa_cfs` | CAP &lt;parameter valueName='WarningLevel'&gt; (not CAP &lt;severity&gt;, which is often literally 'Unknown') | 3 | 3 | 2026-11-02 |
| `tas_fire` | phrase in ALERT_TYPE / EVENT / ALERT_SUMMARY text | 2 | 3 | 2026-11-01 |
| `vic_emergency` | warnings: properties.category1; incidents: none (always 'unknown') | 5 | 3 | 2026-11-02 |
| `wa_dfes` | warnings: phrase in the item title; incidents: none of its own, enriched from a warning sharing the CAD incident number | 5 | 3 | 2026-08-26 |

## act_esa

- **Jurisdiction:** ACT
- **Format:** RSS 2.0 + georss:point
- **Feed URL(s):**
  - https://esa.act.gov.au/feeds/currentincidents.xml
- **Last verified:** 2026-08-26 (from the adapter's own docstring)
- **Snapshot fixture:** `tests/fixtures/emergency_alerts/act_esa/`

### Severity

- **Source field:** none - the ESA incident feed carries no warning level
- **Map:** none - severity is always `unknown` for this source.

### Alert type

'bushfire' when the incident &lt;type&gt; contains BUSHFIRE, else 'other'.

### Data-quality checks

- **Freshness:** the heartbeat warns `STALE` if the newest source-side timestamp across everything the feed lists is older than 24 h.
- **Expected on every kept alert:** `updated_at_src`. The heartbeat warns `FIELD DRIFT` if one is missing on all of them (3 or more alerts).

### Deliberate exclusions

Counted as `excluded_<reason>` in the drop ledger; an all-excluded feed is reported as quiet (`ok`), not broken.

| Ledger reason | Field | Match | Decided |
| --- | --- | --- | --- |
| `excluded_ambulance_mva` | &lt;type&gt; | in ('AMBULANCE RESPONSE', 'MOTOR VEHICLE ACCIDENT') | Captain-directed 2026-08-26 |
| `excluded_hazard_reduction` | &lt;type&gt; | contains 'HAZARD REDUCTION' | Captain-directed 2026-08-26 |

### Known gaps

- INCIDENTS ONLY: per ESA this feed 'does not include warning and alert information', so no Advice / Watch and Act / Emergency Warning is monitored for ACT and severity is always 'unknown'. The portal shows ACT coverage as partial (alertCoverage.ts INCIDENTS_ONLY_SOURCES).
- Updated timestamps ('19 Aug 2026 23:24:36.053') carry no timezone/offset. MEASURED 2026-11-06: they are local Canberra time (stored as UTC they landed ~11 h in the future), so they are read in Australia/Sydney (same daylight-saving rules) from that date. Rows written before then stay ~10-11 h ahead until re-written; expired ones are not backfilled.

## bom_*

- **Jurisdiction:** NSW, NT, QLD, SA, TAS, VIC, WA, ACT (one feed each)
- **Source keys:** `bom_nsw`, `bom_nt`, `bom_qld`, `bom_sa`, `bom_tas`, `bom_vic`, `bom_wa`, `bom_act`
- **Format:** RSS 2.0 per state, plus one HTML bulletin page per item (detail); CAP-AU 1.2 messages from the WMO alert hub index as an enrichment (event, urgency, certainty, severity)
- **Feed URL(s):**
  - https://www.bom.gov.au/fwo/IDZ00054.warnings_nsw.xml
  - https://www.bom.gov.au/fwo/IDZ00055.warnings_nt.xml
  - https://www.bom.gov.au/fwo/IDZ00056.warnings_qld.xml
  - https://www.bom.gov.au/fwo/IDZ00057.warnings_sa.xml
  - https://www.bom.gov.au/fwo/IDZ00058.warnings_tas.xml
  - https://www.bom.gov.au/fwo/IDZ00059.warnings_vic.xml
  - https://www.bom.gov.au/fwo/IDZ00060.warnings_wa.xml
  - https://www.bom.gov.au/fwo/IDZ00085.warnings_act.xml
  - https://severeweather.wmo.int/v2/cap-alerts/au-bom-en/rss.xml
- **Last verified:** 2026-08-27 (from the adapter's own docstring)
- **Snapshot fixture:** `tests/fixtures/emergency_alerts/bom_nsw/`

### Severity

- **Source field:** none - the BOM feed carries no AWS tier (always 'unknown')
- **Map:** none - severity is always `unknown` for this source.

### Alert type

product name in the title, first match: FLOOD -&gt; flood; FIRE WEATHER -&gt; bushfire; TROPICAL CYCLONE -&gt; cyclone; TSUNAMI -&gt; tsunami; SEVERE THUNDERSTORM / DAMAGING WIND / GALE / STORM -&gt; storm; SEVERE WEATHER -&gt; severe_weather.

### Data-quality checks

- **Freshness:** not checked (this source can legitimately go quiet for days).
- **Expected on every kept alert:** `updated_at_src`. The heartbeat warns `FIELD DRIFT` if one is missing on all of them (3 or more alerts).

### Deliberate exclusions

Counted as `excluded_<reason>` in the drop ledger; an all-excluded feed is reported as quiet (`ok`), not broken.

| Ledger reason | Field | Match | Decided |
| --- | --- | --- | --- |
| `excluded_agricultural` | title | contains FROST or SHEEP GRAZIERS | adapter rule 2026-08-27 (agricultural, not public emergency) |
| `excluded_marine` | title | contains MARINE | adapter rule 2026-08-27 (mariner-specific, out of land-based scope) |
| `excluded_unmatched_product` | title | no product keyword matches (e.g. Hazardous Surf Warning) | adapter rule 2026-08-27 ('never guessed into a bucket') |

### Known gaps

- No AWS tier (Advice / Watch and Act / Emergency Warning) exists in BOM's feed, so every BOM row is severity 'unknown'; BOM's own flood intensity words (Minor / Moderate / Major) are a different scale and are not mapped. High-attention emails use the platform's own bom_attention label.
- Products whose name matches no keyword are dropped (counted excluded_unmatched_product), so a NEW BOM warning product is invisible until a keyword is added.
- Needs a browser-shaped User-Agent (BOM 403s the shared default); detail pages are best-effort and fall back to a title-only alert.
- The detail-page 'Issued at' line varies by state (AEST, bare EST/EDT, long 'Australian Eastern Daylight Time', trailing full stop, or no timezone at all on bom_wa); fixed 2026-11-06 after 57 of 91 stored rows had issued_at NULL. A line with no timezone is read as the state's local time only for states without daylight saving (WA +8, QLD +10, NT +9:30); NSW/VIC/SA/TAS/ACT lines with no timezone stay unparsed (issued_at NULL) rather than guessed. emergency_alerts._issued_text still reads the stored text as a fallback.
- CAP fields (cap_event / cap_urgency / cap_certainty / cap_severity) come from the WMO mirror of BoM's CAP-AU stream (bom_cap.py), matched to each RSS alert by warning type plus location words, or by a unique same-type message sent within 90 s of the RSS pubDate for the same state. The RSS items and bulletin pages carry no product code, so the match is conservative: ambiguous or unmatched alerts keep no CAP fields (18 of 24 non-marine items matched when measured 2026-11-06, none wrongly; unmatched were older QLD flood warnings beyond the index's ~8-day window). BoM CAP severity is a different scale from our tier and is never used for it; urgency and certainty are often 'Unknown'. The CAP messages validate against the OASIS CAP 1.2 XSD (120 of 120 sampled) and carry the CAP-AU profile markers; the CAP-AU XSD itself was not obtainable. There are no polygons (BoM area codes only). Personal-use only (BoM's RSS terms limit reuse); set EMERGENCY_ALERTS_BOM_CAP=0 to switch the enrichment off. An outage keeps the RSS-only alerts and logs a warning (no FIELD DRIFT check, since coverage is partial by design).
- BOM cross-lists some border-river warnings in neighbouring states' feeds, so one product can appear under two source_keys (canonical_url is left empty to avoid the unique-index clash).

## nsw_rfs

- **Jurisdiction:** NSW
- **Format:** GeoJSON FeatureCollection (primary) + CAP-AU 1.2 in an EDXL-DE wrapper (enrichment: event, urgency, certainty, severity)
- **Feed URL(s):**
  - https://www.rfs.nsw.gov.au/feeds/majorIncidents.json
  - https://www.rfs.nsw.gov.au/feeds/majorIncidentsCAP.xml
- **Last verified:** 2026-08-26 (from the adapter's own docstring)
- **Snapshot fixture:** `tests/fixtures/emergency_alerts/nsw_rfs/`

### Severity

- **Source field:** properties.category (Advice / Watch and Act / Emergency Warning)
- **Map** (checked in this order; anything else stays `unknown` and is counted as `unmapped_<label>`):

| Source label | Severity |
| --- | --- |
| `advice` | `advice` |
| `watch and act` | `watch_and_act` |
| `emergency warning` | `emergency_warning` |

### Alert type

Always 'bushfire' (Major Incidents feed).

### Data-quality checks

- **Freshness:** the heartbeat warns `STALE` if the newest source-side timestamp across everything the feed lists is older than 72 h.
- **Expected on every kept alert:** `updated_at_src`, `canonical_url`, `cap_urgency`. The heartbeat warns `FIELD DRIFT` if one is missing on all of them (3 or more alerts).

### Deliberate exclusions

Counted as `excluded_<reason>` in the drop ledger; an all-excluded feed is reported as quiet (`ok`), not broken.

| Ledger reason | Field | Match | Decided |
| --- | --- | --- | --- |
| `excluded_hazard_reduction` | properties.description TYPE | == 'Hazard Reduction' | Captain-directed 2026-08-26 |
| `excluded_not_applicable` | properties.category | == 'Not Applicable' (case-insensitive) | 2026-08-26, same class as QLD 'Information' (Captain-directed) |

### Known gaps

- CAP fields come from majorIncidentsCAP.xml (nsw_rfs_cap.py), joined on the RFS incident id. They are an enrichment only: the GeoJSON decides which alerts exist and their tier. If the CAP feed is down the alerts are kept without CAP fields and a FIELD DRIFT warning (cap_urgency missing on every alert) is raised. The CAP feed has no tier mapping of its own that we use: its severity/urgency are stored as given (cap_severity is not the AWS tier).
- Timestamps (properties.pubDate) are DD/MM/YYYY H:MM:SS AM/PM with no timezone/offset. MEASURED 2026-11-06 against stored rows: they behave as UTC (no row ahead of the time it was seen; freshest ~0.1 h old), so they are stored as written. If NSW ever starts sending local time this would show as rows hours in the future.
- A category label outside Advice / Watch and Act / Emergency Warning / Not Applicable is kept at severity 'unknown' and counted as unmapped_&lt;label&gt;.

## nt_securent

- **Jurisdiction:** NT
- **Format:** none (not monitored)
- **Feed URL(s):** none
- **Last verified:** 2026-11-01 (from the adapter's own docstring)

### Severity

- **Source field:** none - NT fire/emergency alerts are not monitored
- **Map:** none - severity is always `unknown` for this source.

### Alert type

n/a (stub returns no alerts; heartbeat is 'skipped').

### Data-quality checks

- **Freshness:** not checked (this source can legitimately go quiet for days).
- **Expected fields:** none checked.

### Deliberate exclusions

None.

### Known gaps

- NOT MONITORED: securent.nt.gov.au answers automated requests with a Cloudflare challenge (HTTP 403) and no public API/RSS/CAP feed was found. The challenge is a bot check and is deliberately NOT bypassed; the route is a sanctioned feed or allowlisted fetch from NT Government (PFES / Bushfires NT / Secure NT) or BoM's CAP-AU.
- BOM weather warnings for NT (bom_nt) are still monitored.

## qld_fire

- **Jurisdiction:** QLD
- **Format:** GeoJSON FeatureCollection
- **Feed URL(s):**
  - https://publiccontent-gis-psba-qld-gov-au.s3.amazonaws.com/content/Feeds/BushfireCurrentIncidents/bushfireAlert.json
- **Last verified:** 2026-08-26 (from the adapter's own docstring)
- **Snapshot fixture:** `tests/fixtures/emergency_alerts/qld_fire/`

### Severity

- **Source field:** properties.WarningLevel (Advice / Watch and Act / Emergency Warning)
- **Map** (checked in this order; anything else stays `unknown` and is counted as `unmapped_<label>`):

| Source label | Severity |
| --- | --- |
| `advice` | `advice` |
| `watch and act` | `watch_and_act` |
| `emergency warning` | `emergency_warning` |

### Alert type

Always 'bushfire' (Bushfire Warnings feed).

### Data-quality checks

- **Freshness:** not checked (this source can legitimately go quiet for days).
- **Expected on every kept alert:** `issued_at`, `updated_at_src`. The heartbeat warns `FIELD DRIFT` if one is missing on all of them (3 or more alerts).

### Deliberate exclusions

Counted as `excluded_<reason>` in the drop ledger; an all-excluded feed is reported as quiet (`ok`), not broken.

| Ledger reason | Field | Match | Decided |
| --- | --- | --- | --- |
| `excluded_hazard_reduction` | properties.CallToAction | contains 'hazard reduction' (case-insensitive) | Captain-directed 2026-08-26 (widened) |
| `excluded_information` | properties.WarningLevel | == 'Information' (case-insensitive) | Captain-directed 2026-08-26 |

### Known gaps

- No per-item URL in the feed (every warning shares one dashboard page), so canonical_url is left empty and dedupe relies on (source_key, event_key) only.
- A WarningLevel outside Advice / Watch and Act / Emergency Warning / Information is kept at severity 'unknown' and counted as unmapped_&lt;label&gt;.

## sa_cfs

- **Jurisdiction:** SA
- **Format:** Atom feed embedding CAP 1.2 (CAP-AU) &lt;alert&gt; blocks
- **Feed URL(s):**
  - https://data.eso.sa.gov.au/feeds/prod/cap-au.xml
- **Last verified:** 2026-11-02 (from the adapter's own docstring)
- **Snapshot fixture:** `tests/fixtures/emergency_alerts/sa_cfs/`

### Severity

- **Source field:** CAP &lt;parameter valueName='WarningLevel'&gt; (not CAP &lt;severity&gt;, which is often literally 'Unknown')
- **Map** (checked in this order; anything else stays `unknown` and is counted as `unmapped_<label>`):

| Source label | Severity |
| --- | --- |
| `advice` | `advice` |
| `watch and act` | `watch_and_act` |
| `emergency warning` | `emergency_warning` |

### Alert type

Always 'bushfire'.

### Data-quality checks

- **Freshness:** the heartbeat warns `STALE` if the newest source-side timestamp across everything the feed lists is older than 72 h.
- **Expected on every kept alert:** `issued_at`, `location`. The heartbeat warns `FIELD DRIFT` if one is missing on all of them (3 or more alerts).

### Deliberate exclusions

Counted as `excluded_<reason>` in the drop ledger; an all-excluded feed is reported as quiet (`ok`), not broken.

| Ledger reason | Field | Match | Decided |
| --- | --- | --- | --- |
| `excluded_hazard_reduction` | CAP &lt;headline&gt; | burn off / planned burn / hazard reduction / prescribed burn | Captain-directed 2026-08-26 (planned burns) |
| `excluded_hazmat` | CAP &lt;category&gt; / &lt;event&gt; / &lt;headline&gt; | category CBRNE, or 'hazardous materials' in event/headline | Captain-directed 2026-08-26 |
| `excluded_structure_fire` | CAP &lt;event&gt; | == 'structure fire' | Captain-directed 2026-08-26 (widened to bushfire only) |

### Structural failures

Counted as `invalid_<reason>`; if items were seen and ALL failed this way the source is reported `failed` and nothing is expired.

- `invalid_missing_cap_alert`
- `invalid_missing_content`

### CAP fields retained

Carried on `CanonicalAlert` (never inferred for other sources); stored in the `alerts` cap_* columns (migration 0250) by default; set `EMERGENCY_ALERTS_CAP_FIELDS=0` only for a database without those columns.

| Field | Source |
| --- | --- |
| `cap_urgency` | CAP &lt;info&gt;&lt;urgency&gt; |
| `cap_certainty` | CAP &lt;info&gt;&lt;certainty&gt; |
| `cap_severity` | CAP &lt;info&gt;&lt;severity&gt; (often literally 'Unknown' - kept verbatim) |
| `cap_event` | CAP &lt;info&gt;&lt;event&gt; |

### Known gaps

- The live WarningLevel is 'Incident' on every entry (2026-11-06), which is not an AWS tier, so SA rows are severity 'unknown' in practice. 'Incident' is treated as a known non-tier label, not counted as unmapped.
- The feed keeps closed incidents with Status COMPLETE; this is read into `closed` so they expire (absence-based expiry would never see them).
- A feed-retirement notice raises (FeedRetiredError) so a dead feed fails the heartbeat; the earlier URL was retired this way.

## tas_fire

- **Jurisdiction:** TAS
- **Format:** ArcGIS REST layer query (JSON, WGS84)
- **Feed URL(s):**
  - https://services.thelist.tas.gov.au/arcgis/rest/services/Public/EmergencyManagementPublic/MapServer/72/query?where=1%3D1&outFields=*&outSR=4326&f=json
- **Last verified:** 2026-11-01 (from the adapter's own docstring)
- **Snapshot fixture:** `tests/fixtures/emergency_alerts/tas_fire/`

### Severity

- **Source field:** phrase in ALERT_TYPE / EVENT / ALERT_SUMMARY text
- **Map** (checked in this order; anything else stays `unknown` and is counted as `unmapped_<label>`):

| Source label | Severity |
| --- | --- |
| `emergency warning` | `emergency_warning` |
| `watch and act` | `watch_and_act` |
| `watch & act` | `watch_and_act` |
| `advice` | `advice` |

### Alert type

keyword in the same text: flood / cyclone / storm / heat -&gt; heatwave / fire or smoke -&gt; bushfire, else 'other'.

### Data-quality checks

- **Freshness:** not checked (this source can legitimately go quiet for days).
- **Expected on every kept alert:** `issued_at`. The heartbeat warns `FIELD DRIFT` if one is missing on all of them (3 or more alerts).

### Deliberate exclusions

Counted as `excluded_<reason>` in the drop ledger; an all-excluded feed is reported as quiet (`ok`), not broken.

| Ledger reason | Field | Match | Decided |
| --- | --- | --- | --- |
| `excluded_expired_at_source` | EXPIRES_DATE | &lt; now | adapter rule: already expired at the source (absence ends any prior record) |
| `excluded_hazard_reduction` | ALERT_TYPE / EVENT / ALERT_SUMMARY / FULL_DESCRIPTION | planned burn / back-burn / fuel reduction / hazard reduction / prescribed burn | Captain-directed (same rule as nsw_rfs); date not recorded in source |

### Structural failures

Counted as `invalid_<reason>`; if items were seen and ALL failed this way the source is reported `failed` and nothing is expired.

- `invalid_missing_headline`

### Known gaps

- Only one record (a 'Smoke Alert') was live when the adapter was written, so the full ALERT_TYPE vocabulary is NOT confirmed; wording that states no AWS tier stays 'unknown' and is counted as unmapped_&lt;ALERT_TYPE&gt;.
- A layer-level error object in the response raises (heartbeat fails) rather than reading as 'no alerts'.
- Timezone: the epoch-ms date fields are LOCAL Hobart wall-clock time written as UTC. MEASURED 2026-11-06 (stored issued_at ~10.8 h after first seen). Read in Australia/Hobart from that date, which also corrects the 'already expired at source' check that used to lag ~11 h. Rows written before then stay ahead until re-written.

## vic_emergency

- **Jurisdiction:** VIC
- **Format:** incidents: JSON (results[]); warnings: GeoJSON FeatureCollection (events feed)
- **Feed URL(s):**
  - https://data.emergency.vic.gov.au/Show?pageId=getIncidentJSON
  - https://www.emergency.vic.gov.au/public/events-geojson.json
- **Last verified:** 2026-11-02 (from the adapter's own docstring)
- **Snapshot fixture:** `tests/fixtures/emergency_alerts/vic_emergency/`

### Severity

- **Source field:** warnings: properties.category1; incidents: none (always 'unknown')
- **Map** (checked in this order; anything else stays `unknown` and is counted as `unmapped_<label>`):

| Source label | Severity |
| --- | --- |
| `emergency warning` | `emergency_warning` |
| `watch and act` | `watch_and_act` |
| `watch & act` | `watch_and_act` |
| `advice` | `advice` |

### Alert type

incidents: incidentType (BUSH/GRASS -&gt; bushfire; STRUCTURE -&gt; structure_fire; else other, then dropped); warnings: CAP event (fire/flood/cyclone/storm/heat/tsunami/thunderstorm asthma).

### Data-quality checks

- **Freshness:** the heartbeat warns `STALE` if the newest source-side timestamp across everything the feed lists is older than 48 h.
- **Expected on every kept alert:** `updated_at_src`. The heartbeat warns `FIELD DRIFT` if one is missing on all of them (3 or more alerts).

### Deliberate exclusions

Counted as `excluded_<reason>` in the drop ledger; an all-excluded feed is reported as quiet (`ok`), not broken.

| Ledger reason | Field | Match | Decided |
| --- | --- | --- | --- |
| `excluded_false_alarm` | incidents incidentType | contains 'FALSE ALARM' | adapter rule (date not recorded in source) |
| `excluded_hazard_reduction` | incidents incidentType / name | planned burn / burn-off / hazard reduction / prescribed burn | Captain-directed 2026-08-26 (planned burns, applied here as a guard) |
| `excluded_not_warning_feedtype` | events feed properties.feedType | != 'warning' (incident / planned burn / earthquake features) | design (module docstring): only warnings are taken from the events feed |
| `excluded_other_type` | incidents incidentType / category1 | classified 'other' (Non-Structure, Accident / Rescue, ...) | Captain-directed 2026-08-26 |
| `excluded_structure_fire` | incidents incidentType | classified 'structure_fire' | Captain-directed 2026-08-26 (widened to bushfire only) |

### Structural failures

Counted as `invalid_<reason>`; if items were seen and ALL failed this way the source is reported `failed` and nothing is expired.

- `invalid_missing_id`

### CAP fields retained

Carried on `CanonicalAlert` (never inferred for other sources); stored in the `alerts` cap_* columns (migration 0250) by default; set `EMERGENCY_ALERTS_CAP_FIELDS=0` only for a database without those columns.

| Field | Source |
| --- | --- |
| `cap_urgency` | warnings: properties.cap.urgency |
| `cap_certainty` | warnings: properties.cap.certainty |
| `cap_severity` | warnings: properties.cap.severity |
| `cap_event` | warnings: properties.cap.event (incident rows carry no CAP block: all four are null) |

### Known gaps

- Incident timestamps are DD/MM/YYYY with no timezone/offset. MEASURED 2026-11-06: they are local Melbourne time (stored as UTC they landed ~11 h in the future), so they are read in Australia/Melbourne from that date. Rows written before then stay ~10-11 h ahead until re-written (active alerts are re-written every run; expired ones are not backfilled).
- The incidents feed has no warning level, so incident rows are always severity 'unknown'; only the events feed's warning features carry a real tier.
- A warning's category1 outside Advice / Watch and Act / Emergency Warning is kept at severity 'unknown' and counted as unmapped_&lt;label&gt;.

## wa_dfes

- **Jurisdiction:** WA
- **Format:** RSS 2.0 (dfes:/geo:/georss: extensions); two feeds
- **Feed URL(s):**
  - https://api.emergency.wa.gov.au/v1/rss/warnings
  - https://api.emergency.wa.gov.au/v1/rss/incidents
- **Last verified:** 2026-08-26 (from the adapter's own docstring)
- **Snapshot fixture:** `tests/fixtures/emergency_alerts/wa_dfes/`

### Severity

- **Source field:** warnings: phrase in the item title; incidents: none of its own, enriched from a warning sharing the CAD incident number
- **Map** (checked in this order; anything else stays `unknown` and is counted as `unmapped_<label>`):

| Source label | Severity |
| --- | --- |
| `emergency warning` | `emergency_warning` |
| `watch and act` | `watch_and_act` |
| `advice` | `advice` |

### Alert type

warnings: BUSHFIRE / STORM / CYCLONE / FLOOD / HEATWAVE in the title (first match, Heatwave added 2026-11-06), anything else dropped; incidents: 'bushfire' only.

### Data-quality checks

- **Freshness:** the heartbeat warns `STALE` if the newest source-side timestamp across everything the feed lists is older than 48 h.
- **Expected on every kept alert:** `updated_at_src`, `canonical_url`. The heartbeat warns `FIELD DRIFT` if one is missing on all of them (3 or more alerts).

### Deliberate exclusions

Counted as `excluded_<reason>` in the drop ledger; an all-excluded feed is reported as quiet (`ok`), not broken.

| Ledger reason | Field | Match | Decided |
| --- | --- | --- | --- |
| `excluded_hazard_reduction` | title type (warnings and incidents) | contains 'BURN OFF' | Captain-directed 2026-08-26 (Burn Off = Hazard Reduction) |
| `excluded_hazmat` | title type (warnings and incidents) | contains 'HAZMAT' | Captain-directed 2026-08-26 |
| `excluded_not_bushfire` | incidents title type | does not contain 'BUSHFIRE' (e.g. Structure Fire, Vehicle Fire) | Captain-directed 2026-08-26 (widened to bushfire only) |
| `excluded_other_type` | warnings title | none of BUSHFIRE / STORM / CYCLONE / FLOOD / HEATWAVE (e.g. Smoke Alert) | Captain-directed 2026-08-26 (platform-wide 'Other' exclusion) |
| `excluded_park_closure` | title type (warnings and incidents) | contains 'FACILITY OR PARK CLOSURE' or 'PARK CLOSURE' | Captain-directed 2026-08-26 |

### Known gaps

- Warning types outside bushfire / storm / cyclone / flood / heatwave are dropped by design, which includes real public Smoke Alert warnings (seen live 2026-11-06; Captain chose to keep dropping them while ingesting Heatwave Advice). Recorded as excluded_other_type, not as unmapped.
- Incidents carry no warning level; severity is only known when the CAD-ID also appears as dfes:incidentNumber on a warning.
- A warning title with no recognised level phrase is kept at severity 'unknown' and counted as unmapped_&lt;label&gt;.
