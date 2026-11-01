# Mission 5 — `capacity_preferences` read contract (WS2)

Table: `public.capacity_preferences` (migration 0218). Explicit Captain
correction store — outranks historical/inferred evidence for the same item.

## Columns you read

`domain` (text, `'capacity' | 'ready_room'`), `item_code` (text, references
`capacity_interventions.intervention_id`, nullable), `preference_state`
(`'preferred' | 'do_not_suggest'`), `note`, `source`
(`'captain_stated' | 'inferred'`), `updated_by`.

## Query shape

```sql
select item_code, preference_state
from capacity_preferences
where domain = 'ready_room'
  and item_code is not null;
```

Build `{item_code: preference_state}` from the result.

## Filter rule (apply exactly this order, do not blend into a score)

1. Drop any candidate whose `item_code` maps to `'do_not_suggest'` —
   before scoring, regardless of positive historical evidence.
2. After your own ranking/scoring, move any `'preferred'` candidate ahead
   of every non-preferred one (stable tie-break-first), without changing
   its score or reordering within the preferred/non-preferred groups.

Absence of a row is not an implicit `do_not_suggest` — no correction made.

## Writes

Not in this stream's scope; capacitybot writes via
`intervention_engine.set_preference()`. If Ready Room needs to write, use
the same upsert-on-`(domain, item_code)` pattern (unique index is partial:
`where item_code is not null`) and default `source='captain_stated'`
unless explicitly writing a platform-inferred row.
