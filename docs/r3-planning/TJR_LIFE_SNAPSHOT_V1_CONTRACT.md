# TJR Life snapshot, contract v1.1 (v1.0 below, unchanged except where marked)

v1.1 adds optional fields to the `alerts` section only. See "Contract v1.1" at the end. Same route, same auth, same transport statuses.

`GET /api/integrations/tjr-life/v1/snapshot` with `Authorization: Bearer <Supabase access token>`.
Bearer-only, GET-only, Captain-only. Read-only. All keys snake_case at every level.
Responses carry `Cache-Control: private, no-store`.

## Transport statuses
| Status | Body | Meaning |
|---|---|---|
| 200 | snapshot | Authenticated. Always 200 even if every section is unavailable. |
| 401 | `{"error":"Unauthorized"}` | Missing, malformed, invalid or expired token. Refresh and retry once. |
| 403 | `{"error":"Forbidden"}` | Not the Captain, or the feature is switched off (kill switch). Do not retry. |
| 400 | `{"error":"invalid_request"}` | Authenticated request carrying any query string. The snapshot takes no parameters. An unauthenticated request with a query string still gets 401/403 first. |
| 405 | `{"error":"Method not allowed"}` | Anything but GET. |
| 429 | `{"error":"Too many requests"}` + `Retry-After: 60` | More than 30 requests a minute. |
| 503 | `{"error":"Service unavailable"}` | Auth server or configuration unavailable. Keep the session; retry later. |

## Body
```json
{
  "contract_version": "1.0",
  "generated_at": "2026-10-15T02:00:00.000Z",
  "hq_status":    { "generated_at": "...", "summary": "plain text", "state": "ok|degraded|attention|unknown", "error": null },
  "latest_brief": { "generated_at": "... | null", "brief_date": "YYYY-MM-DD | null", "lines": ["plain text", ""], "error": null },
  "alerts":       { "generated_at": "...", "items": [ { "id": "...", "headline": "...", "severity": "...", "occurred_at": "..." } ], "error": null }
}
```
A section that failed is exactly `{"error":"unavailable"}` (no other keys, no detail).
Timestamps are UTC ISO-8601 with milliseconds and a `Z` offset.

## Differences from the proposal (reasons)
1. `hq_status.state` has a fourth value, `attention` (the allowed set is exactly `ok`, `degraded`, `attention`, `unknown`). The HQ interpreter's most severe posture is ATTENTION ("a critical capability is unavailable"). Folding it into `degraded` would understate the worst case on the Captain's phone. An unknown `state` string is not mapped to `unknown`: it makes the whole `hq_status` section malformed, and the client treats that section as unavailable (see Client rules and fixture `malformed-section.json`). The same applies to a `hq_status` with no `state`.
2. `latest_brief.generated_at`, `brief_date` are `null` and `lines` is `[]` when no brief exists yet (distinct from an unavailable section).
3. In `lines`, an empty string `""` marks a paragraph break (never first, last or repeated). Lines are plain text: render as text, never as HTML or Markdown. Text such as `<NRP>` is literal.
4. Section `generated_at` meaning: `hq_status` is when the status was computed, `alerts` is when the query ran, `latest_brief` is when the brief itself was generated (use it to show staleness).

## Field notes
- `hq_status.summary`: the Captain's Chair summary (headline plus capability impact sentences). Static interpreter text; carries no job output or error text. At most 400 characters.
- `latest_brief`: newest `captains_daily_briefs` row of any type. Tags stripped first, then entities decoded. `health_snapshot` is never read. At most 40 lines (the first 40; a trailing paragraph break is dropped) of at most 500 characters each.
- `alerts`: at most 20 active, unexpired rows, newest `issued_at` first (falls back to `first_seen_at`). `id` is at most 64 characters and unique within a response (a longer or repeated id drops that row). `severity` is exactly one of `emergency_warning`, `watch_and_act`, `advice`, `unknown`; any other stored value is sent as `unknown`. `headline` is plain text, 160 characters max. No description, raw text, coordinates, URLs or source details.
- Caps are in UTF-16 code units; a cut never splits a surrogate pair and ends with `…`.
- Total response cap: 64 KB (65,536 bytes of compact UTF-8 JSON). If the caps alone would exceed it (3-byte characters can), the server drops brief lines from the end, then alerts from the end, and as a last resort marks sections `{"error":"unavailable"}`. The pretty-printed fixture file `oversized.json` is slightly larger than 64 KB only because of indentation; its compact form is within the cap (a test checks this).
- Never present: audit rows, mission lists, `created_by`, source `error_message`, job `lastAction` text, OSINT rows.

## Client rules
- If `contract_version` is not `1.x`, do not parse; show "update the app" (fixture `unknown-version.json`).
- Ignore unknown keys at every level (fixture `unknown-keys.json`).
- Sections are independent; show what is available.
- A section that matches neither its shape nor `{"error":"unavailable"}` (wrong type, `lines` not an array, an unknown `state`) is treated as unavailable; do not crash (fixture `malformed-section.json`).

## Fixtures (v1.0)
`fixtures/tjr-life-snapshot-v1/`, seven files plus `SHA256SUMS`: `full`, `degraded`, `all-errored`, `oversized`, `malformed-section`, `unknown-version`, `unknown-keys` (.json). `full`, `degraded`, `all-errored` and `oversized` are generated by the real builder and checked byte-for-byte by the server tests; the other three are hand-authored edge cases. Copy them byte-for-byte; LF line endings, trailing newline. `SHA256SUMS` is checked by a test (`sha256sum -c SHA256SUMS`).

## Contract v1.1 (alerts only)

`contract_version` is `"1.1"`. The change is additive: a v1.0 client that ignores unknown keys keeps working. `hq_status` and `latest_brief` are unchanged. No new route.

### Alerts section
```json
"alerts": {
  "generated_at": "...",
  "last_polled_at": "... | null",
  "items": [ {
    "id": "...", "headline": "...", "severity": "...", "occurred_at": "...",
    "alert_type": "bushfire", "status": "active", "expires_at": "... | null",
    "jurisdiction": "VIC", "updated_at": "...", "source_name": "VIC Emergency"
  } ],
  "error": null
}
```
The v1.0 rules for `id`, `headline`, `severity`, `occurred_at`, the 20-item cap and newest-`issued_at`-first ordering are unchanged.

| Field | Source column | Rule |
|---|---|---|
| `alert_type` | `alert_type` | Always present. One of `bushfire`, `flood`, `storm`, `cyclone`, `heatwave`, `hazard_reduction`, `structure_fire`, `severe_weather`, `tsunami`, `other`. Any other value is sent as `other`. |
| `status` | `status` | Always present. One of `new`, `active`, `updated`, `superseded`, `expired`, `inactive`, `errored`. Any other value is sent as `unknown`. |
| `expires_at` | `expiry` | Always present. ISO-8601 UTC with `Z`, or `null` when there is no expiry. |
| `jurisdiction` | `jurisdiction` | Plain text, at most 8 characters. Omitted when missing or blank. |
| `updated_at` | `updated_at_src`, else `last_seen_at` | ISO-8601 UTC with `Z`. Omitted if neither parses. |
| `source_name` | `alert_sources.source_name` (display name) | Plain text, at most 40 characters. Omitted when missing or blank. The source key is never sent. |

`last_polled_at` (section level): the newest `last_seen_at` among active, unexpired alerts, read by one extra one-row query with the user-scoped client. The source heartbeat is not read. It is `null` when there are no active alerts. `last_seen_at` only advances while an alert is still present in its feed, so with no alerts `null` says nothing about whether polling is healthy.

Text caps are in UTF-16 code units, with the same truncation and `…` rule as v1.0. Unknown `alert_type`, `status` and `severity` strings must not crash a client; a client should show them as received-but-unrecognised.

Not sent: `latitude`, `longitude`, `canonical_url`, `raw_text`, `description`, `location`, `event_key`, `emergency_email_sent_at`, feed URLs, source notes, silences.

The 64 KB total cap and its shedding order (brief lines from the end, then alerts from the end, then sections) are unchanged. The new fields make each alert larger, so under the size cap fewer alerts survive than in v1.0 when the brief is at its maximum.

### Facts a client must not hide
- All Bureau of Meteorology warnings arrive with `severity` `unknown`: that feed carries no warning-level field. `unknown` does not mean "no emergency". Show it as an alert of unrated severity, never as nothing or as low risk.
- An empty `items` list is not a statement that nothing is happening. The TAS and NT sources have no working adapter yet (`NOT_YET_IMPLEMENTED` in the adapter code), so those jurisdictions can never contribute alerts. The WA, VIC, NSW, QLD, SA and ACT adapters exist. Whether a given feed is being read right now is not reported by the snapshot.
- The list is capped at 20, newest `issued_at` first, not ordered by severity. With more than 20 active alerts, a high-severity alert issued earlier can be absent.

### Fixtures (v1.1)
`fixtures/tjr-life-snapshot-v1_1/`, seven files plus `SHA256SUMS`: `full`, `degraded`, `all-errored`, `oversized` (generated by the real builder and checked byte-for-byte by tests), and `unknown-keys`, `malformed-section`, `unknown-version` (hand-authored; `malformed-section` shows an unknown `hq_status.state` and a non-array `lines` and `items`, each making its section unavailable). The v1.0 fixtures in `fixtures/tjr-life-snapshot-v1/` are unchanged and still describe valid v1.x payloads.
