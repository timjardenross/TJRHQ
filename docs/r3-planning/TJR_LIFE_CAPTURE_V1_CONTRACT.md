# TJR Life capture contract `tjr-life-capture.v1`

Route: `POST /api/integrations/tjr-life/v1/captures` (R3 Delivery 2, slice D2-1). Design and decisions:
TJR-Life-iOS `docs/r3-planning/R3_D2_1_CAPTURE_INGEST_DESIGN.md` (sections 9 and 10). **Off by default.**
Nothing below has been run against production: every "measured" figure is **NOT VERIFIED** until the
product owner runs the test script in the kill-switch runbook.

## Switches and configuration

| Variable | Meaning |
|---|---|
| `MOBILE_WRITE_ENABLED` | Must equal the string `true`, otherwise 403 from both layers. Separate from the read switch. |
| `MOBILE_WRITE_CAPTAIN_USER_ID` | The one Supabase user allowed to write. Separate from the read id; the write path never falls back to it. |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-side only; read in `lib/tjrLifeCaptures.ts` and nowhere else under the TJR Life files (a test pins this). |

## Request

```json
{ "contract_version": "tjr-life-capture.v1", "device_id": "[A-Za-z0-9._-]{1,64}",
  "captures": [ { "client_id": "uuid", "kind": "task|note|idea|commitment",
                  "text": "1..2000 characters, trimmed", "captured_at": "ISO-8601 with Z or offset" } ] }
```

POST only, JSON only, no query string, body at most 128 KB (checked while reading, before parsing),
1 to 20 captures. Unknown fields at any level are rejected, not stored. Identity is never read from the body.

## Behaviour

- Order: Captain bearer check (403 for any other signed-in user, before any database call) -> capped body read ->
  pure validation -> server-side insert with the service-role client.
- **All-or-nothing validation:** any invalid item refuses the whole request (400), and any `health` or `decision`
  item refuses it with 422 `class_not_consented`; nothing is written in either case. This is stricter than the
  design's per-item wording and is deliberate: a policy-refused item signals an app bug and must not leave a
  partial batch behind.
- Inserts are idempotent on `idempotency_key = tjr-life:<client_id>` (the database's partial unique index). A retry or
  race returns `duplicate` with the canonical row id. A database failure on any item answers 503 for the whole
  request; the app retries the whole batch.
- `commitment` is stored as `item_type = task` with `summary = "Commitment (captured in TJR Life)"`.
- Server-controlled: `captured_by` (`tjr_life_ios:<device_id>`), `source_type` (`tjr_life_ios`), `source_channel_id`,
  `source_message_id`, timestamps (a future `captured_at` is clamped to the server time), status fields, classification
  `unclassified`, `idempotency_key`.
- One `audit_events` row per request (counts only, no capture text), best effort.

## Responses

`200 {"results":[{"client_id","status":"accepted|duplicate","hq_id"}],"received_at"}`; errors are generic:
`400 invalid_request`, `401 Unauthorized`, `403 Forbidden`, `405` (with `Allow: POST`), `413 too_large`,
`422 class_not_consented`, `429 Too many requests` (10 per minute per Captain), `503 unavailable`.
Every response carries `Cache-Control: private, no-store` and `Vary: Authorization`. Nothing logs.

## Prerequisite: database migration (separate PR, run only when the product owner says)

`captured_items.source_type` does not yet allow `tjr_life_ios`. Until the owner runs the additive migration, an
enabled route would answer 503 on every insert. Order of operations: merge code (route stays off) -> run migration ->
set `MOBILE_WRITE_CAPTAIN_USER_ID`, then `MOBILE_WRITE_ENABLED=true` -> redeploy.

## Kill switch (summary; fuller table in the runbook)

Set `MOBILE_WRITE_ENABLED` to anything other than `true` and redeploy: 403 from both layers. Unsetting
`MOBILE_WRITE_CAPTAIN_USER_ID` does the same. Revoking the Captain's sessions gives 401.
