-- ============================================================
-- Migration 0166 — Follow-Through audit trail
-- USS Starship Endeavour NCC-170230
--
-- follow_through_events mirrors task_events' shape (migration 0056):
-- an append-only audit trail alongside the mutable personal_tasks row,
-- same established convention in this codebase.
--
-- follow_through_sends is what makes an XO reply-to-reminder resolvable
-- to a task without a session/state layer: engine writes one row per
-- individual (non-bundled) send, XO reads Telegram's own
-- reply_to_message.message_id back against it. Durable across bot
-- restarts (cmd_restart_bots already restarts tg-xo.service routinely),
-- unlike an in-process dict.
--
-- Additive & idempotent. Safe to re-run.
-- ============================================================

CREATE TABLE IF NOT EXISTS follow_through_events (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id     uuid        NOT NULL REFERENCES personal_tasks(id) ON DELETE CASCADE,
    event_type  text        NOT NULL CHECK (event_type IN (
                    'surfaced', 'done', 'snoozed', 'deferred', 'blocked',
                    'decomposed', 'dropped', 'nl_capture', 'nl_update'
                )),
    detail      jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE follow_through_events IS
  'Append-only audit trail for Adaptive Follow-Through, mirrors '
  'task_events'' shape (migration 0056). Powers section 17 history and '
  'is the raw data for future follow-through-intensity learning '
  '(section 18) — not read by V1 beyond the daily-cap count.';

CREATE INDEX IF NOT EXISTS idx_follow_through_events_task
    ON follow_through_events (task_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_follow_through_events_type_occurred
    ON follow_through_events (event_type, occurred_at DESC);

ALTER TABLE follow_through_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_full_access" ON follow_through_events;
CREATE POLICY "service_role_full_access" ON follow_through_events
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "authenticated_full_access" ON follow_through_events;
CREATE POLICY "authenticated_full_access" ON follow_through_events
    FOR ALL TO authenticated USING (true) WITH CHECK (true);


CREATE TABLE IF NOT EXISTS follow_through_sends (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id    uuid        NOT NULL REFERENCES personal_tasks(id) ON DELETE CASCADE,
    chat_id    text        NOT NULL,
    message_id bigint      NOT NULL,
    sent_at    timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE follow_through_sends IS
  'One row per individual (non-bundled) reminder XO actually sent. '
  'Lets a Telegram reply (update.message.reply_to_message.message_id) '
  'resolve back to the task it was about, without an in-memory session '
  'layer that would die on tg-xo.service restarts.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_follow_through_sends_chat_message
    ON follow_through_sends (chat_id, message_id);
CREATE INDEX IF NOT EXISTS idx_follow_through_sends_task
    ON follow_through_sends (task_id);

ALTER TABLE follow_through_sends ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_full_access" ON follow_through_sends;
CREATE POLICY "service_role_full_access" ON follow_through_sends
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "authenticated_full_access" ON follow_through_sends;
CREATE POLICY "authenticated_full_access" ON follow_through_sends
    FOR ALL TO authenticated USING (true) WITH CHECK (true);
