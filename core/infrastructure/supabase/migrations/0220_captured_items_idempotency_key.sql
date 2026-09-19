-- 0220_captured_items_idempotency_key.sql
--
-- Mission 6B closure-pass fix (Captain-mandated, not residual debt): the
-- executable dispatch-scenario proof for Number One's "remember" intent
-- showed that a retried capture mutation (e.g. a network-retried POST)
-- creates a second captured_items row for the same logical Captain
-- action — violating the programme invariant "infrastructure retry must
-- not create multiple logical objects from one Captain action."
--
-- This is deliberately a Mission 3 canonical-Capture-owned fix, not a
-- Number One-specific mechanism: idempotency_key lives on captured_items
-- itself, so ANY capture channel (Telegram voice/text, Portal quick
-- capture, Number One's dispatcher, a future channel) gets the same
-- retry-safety by supplying a key — Number One is just the first caller
-- to actually pass one (lcars-portal/src/lib/number-one/canonical-
-- actions.ts's captureNote()). Existing capture paths that don't supply a
-- key are completely unaffected (nullable column, partial unique index).
--
-- Mechanism: an explicit identity (a request/message id), not fuzzy
-- content deduplication — two captures with identical text but different
-- keys are two legitimate captures (the Captain choosing to record the
-- same thing again later); two captures with the SAME key are one retried
-- request. The partial unique index is the actual safety mechanism (not
-- application-level "check then insert", which races) — a second insert
-- with the same key fails atomically at the database under concurrent
-- duplicate requests, and the caller falls back to reading the row that
-- won, so every retry/race path converges on exactly one canonical row.
alter table captured_items add column if not exists idempotency_key text;

comment on column captured_items.idempotency_key is
  'Optional caller-supplied request identity (e.g. a chat message id) for retry-safety. NULL for capture channels that do not supply one (unaffected, pre-existing behaviour). Never used for fuzzy/content-based deduplication — an exact key match only.';

create unique index if not exists captured_items_idempotency_key_uidx
  on captured_items(idempotency_key)
  where idempotency_key is not null;
