# Forward watch, generated 2026-11-24 (horizon 42 days to 2027-01-05)

Source: sample export read 2026-11-24 via read-only SELECT (not the full corpus; see docs/INTEL-PRODUCTS-2026-11-24.md limitations). 1598 rows read. Offline, read-only, default OFF, not wired into any service.

This lists dated events that sources state explicitly. It is not a forecast: nothing here predicts an outage, a regulatory decision or a vendor action. Dates come from the source text; no date is inferred. A scheduled item can still be moved or cancelled, and each carries an uncertainty label.

Uncertainty labels: **SCHEDULED_BY_OWNER** = owner-published window; can be moved or cancelled; **OFFICIAL_DATE_STATED** = official source states the date; subject to amendment; **RELAYED_BY_NEWS** = secondary report; not checked against the primary source; **DATE_PRECISION_MONTH** = only the month is stated; **DATE_NOT_STATED** = planned event announced, no date in the export.

## Coverage

- [OBSERVED FACT] Authoritative items in horizon: 14 (maintenance 14, deadline 0, lifecycle 0, regulatory_effective 0); from official/regulator sources: 0.
- [OBSERVED FACT] Secondary (news) items with an explicit future date: 0. Dated items beyond the horizon: 0.
- [OBSERVED FACT] Planned events with no stated date (official sources): 1.
- No regulator consultation deadline, regulator effective date, vendor end-of-life notice or AEMO forward notice with an explicit future date was found in this export. That is a statement about the export, not about the world: the feeds may not carry such items, or may state them without a year.

## Authoritative items by week

### Week commencing 2026-11-23

| Date | Source | Item | Basis and quote | Uncertainty | Event id |
|---|---|---|---|---|---|
| 2026-11-25 09:00 PST | Twilio Status | Malaysia SMS Carrier Partner Maintenance | provider's own status feed; date read from text; cue type 'maintenance': "partner in Malaysia is conducting an emergency maintenance from 25 November 2026 at 09:00 PST until 25 Novemb" | SCHEDULED_BY_OWNER | `1614a430-a067-4ded-b1b0-9a6b33118ebb` |
| 2026-11-25 11:00 PST | Twilio Status | France SMS Carrier Partner Maintenance | provider's own status feed; date read from text; cue type 'maintenance': "carrier partner in France is conducting a planned maintenance from 25 November 2026 at 11:00 PST until 25 November 20" | SCHEDULED_BY_OWNER | `a398287f-e991-48e4-9ce7-24867d957202` |
| 2026-11-25 18:45 PST | Twilio Status | Puerto Rico SMS Carrier Maintenance - Liberty | provider's own status feed; date read from text; cue type 'maintenance': "network in Puerto Rico is conducting a planned maintenance from 25 November 2026 at 18:45 PST until 25 November 2" | SCHEDULED_BY_OWNER | `acb974ce-b218-47ee-af6f-1f0d421e0fae` |

### Week commencing 2026-11-30

| Date | Source | Item | Basis and quote | Uncertainty | Event id |
|---|---|---|---|---|---|
| 2026-11-30 13:00 GMT | Supabase Status | Maintenance: Scheduled maintenance: Shared Pooler (Supavisor), eu-central-2 | provider's own status feed; date read from text; cue type 'maintenance': "Shared Pooler (Supavisor), eu-central-2. Status: Scheduled (Mon, 30 Nov 2026 13:00:00 GMT - Mon, 30 Nov 2026 15:00:00 GMT) We will perform schedul" | SCHEDULED_BY_OWNER | `a1d58dd0-56fe-4126-9011-d33356992233` |
| 2026-11-30 15:00 PST | Twilio Status | Slovenia SMS Carrier Partner Maintenance | provider's own status feed; date read from text; cue type 'maintenance': "carrier partner in Slovenia is conducting a planned maintenance from 30 November 2026 at 15:00 PST until 30 November" | SCHEDULED_BY_OWNER | `4b306149-3087-4e86-9b66-5d2f23e8ca54` |
| 2026-11-30 09:00 PST | Twilio Status | Singapore SMS Carrier Maintenance - SingTel | provider's own status feed; date read from text; cue type 'maintenance': "network in Singapore is conducting a planned maintenance from 30 November 2026 at 09:00 PST until 30 November 202" | SCHEDULED_BY_OWNER | `8ef85ab7-6c59-4416-87a2-addaccb48b7f` |
| 2026-11-30 15:00 PST | Twilio Status | Multiple Destination SMS Carrier Partner Maintenance | provider's own status feed; date read from text; cue type 'maintenance': "in Gabon, Peru and Ecuador is conducting a planned maintenance from 30 November 2026 at 15:00 PST unt" | SCHEDULED_BY_OWNER | `a8e19fcf-7a83-4845-a1a8-c511ae8feae9` |
| 2026-11-30 15:00 PST | Twilio Status | Ecuador SMS Carrier Maintenance - Conecel | provider's own status feed; date read from text; cue type 'maintenance': "Conecel network in Ecuador is conducting a planned maintenance from 30 November 2026 at 15:00 PST until 30 November 2026 at 19:00 PS" | SCHEDULED_BY_OWNER | `d40d4061-db63-476d-a90c-6b559336061d` |
| 2026-12-01 09:00 PST | Twilio Status | Malaysia SMS Carrier Maintenance - Celcom | provider's own status feed; date read from text; cue type 'maintenance': "Celcom network in Malaysia is conducting a planned maintenance from 01 December 2026 at 09:00 PST until 01 December 2026 at 13:00 PST" | SCHEDULED_BY_OWNER | `d8ac3462-705f-433a-bb04-cbd53df8d7aa` |
| 2026-12-03 01:00 PST | Twilio Status | United States MMS Carrier Partner Maintenance | provider's own status feed; date read from text; cue type 'maintenance': "in the United States is conducting a planned maintenance from 03 December 2026 at 01:00 PST until 03 D" | SCHEDULED_BY_OWNER | `28a52baa-0113-4f93-b89d-a67647510a4b` |
| 2026-12-06 | Twilio Status | United Kingdom Account Security Carrier Partner Maintenance - Three | provider's own status feed; date read from text; cue type 'maintenance': "Three United Kingdom is conducting a planned maintenance from 06 December 2026 at" | SCHEDULED_BY_OWNER | `37b0a217-2507-40f9-b455-a6bf0a36a36a` |

### Week commencing 2026-12-07

| Date | Source | Item | Basis and quote | Uncertainty | Event id |
|---|---|---|---|---|---|
| 2026-12-08 13:00 GMT | Supabase Status | Maintenance: Scheduled maintenance: Shared Pooler (Supavisor), eu-north-1 | provider's own status feed; date read from text; cue type 'maintenance': "Shared Pooler (Supavisor), eu-north-1. Status: Scheduled (Tue, 08 Dec 2026 13:00:00 GMT - Tue, 08 Dec 2026 15:00:00 GMT) We will perform schedul" | SCHEDULED_BY_OWNER | `74d19ed5-645a-48e0-b311-4d8206cbb203` |
| 2026-12-09 15:00 GMT | Supabase Status | Maintenance: Scheduled maintenance: Shared Pooler (Supavisor), eu-west-3 | provider's own status feed; date read from text; cue type 'maintenance': "Shared Pooler (Supavisor), eu-west-3. Status: Scheduled (Wed, 09 Dec 2026 15:00:00 GMT - Wed, 09 Dec 2026 17:00:00 GMT) We will perform schedul" | SCHEDULED_BY_OWNER | `5083c408-3e0e-446e-ba28-5d49194f806f` |
| 2026-12-09 13:00 GMT | Supabase Status | Maintenance: Scheduled maintenance: Shared Pooler (Supavisor), eu-west-2 | provider's own status feed; date read from text; cue type 'maintenance': "Shared Pooler (Supavisor), eu-west-2. Status: Scheduled (Wed, 09 Dec 2026 13:00:00 GMT - Wed, 09 Dec 2026 15:00:00 GMT) We will perform schedul" | SCHEDULED_BY_OWNER | `8d72b62d-5766-4c07-8bb4-9fe4ffb32f83` |

## Announced but undated (official sources)

| Source | Item | Uncertainty | Event id |
|---|---|---|---|
| AEMO Market Notices | Initial - CHG0112685 - Planned maintenance affecting the AEMO Market Network. | DATE_NOT_STATED | `bf40ae8e-6e75-4121-bf2e-aedce6a86c17` |

## Relayed by news (not authoritative, not confirmed)

None.

## Limits

- Only explicit dates with a year are read. 'Next Tuesday', 'Q1' and bare 'Dec 8' are ignored, so real events can be missed.
- Times are copied as the source states them (zone as written); this tool does not convert zones.
- Cue words decide whether a date is a planned event. A date inside an unrelated sentence near a cue can be picked up; read the quote.
- CVE/KEV feeds are excluded: their rows carry no scheduled-event dates (KEV due dates are not in the export).
- [UNVERIFIED HYPOTHESIS] Whether a listed window will cause customer impact is not assessed.
