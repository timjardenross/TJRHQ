-- 2026-09-15 adversarial review (Fix Next #10): the /brief Telegram
-- command's regenerate cooldown lived only in a process-global Python
-- variable (_brief_regen_started_at in telegram-bots/xo/app.py) -- a bot
-- restart (deploy, crash, manual) resets it to None, so a regenerate that
-- was already running (the detached subprocess itself survives the
-- restart via start_new_session=True) could get kicked off again by the
-- very next /brief call, doubling the ~15-25min LLM-synthesis cost.
--
-- Small single-purpose table rather than repurposing domain_heartbeats
-- (semantically a health-status table, not a rate-limit/cooldown one).
CREATE TABLE IF NOT EXISTS bot_rate_limits (
  rate_key     text        PRIMARY KEY,
  triggered_at timestamptz NOT NULL
);

ALTER TABLE bot_rate_limits ENABLE ROW LEVEL SECURITY;

-- Service-role only (the XO bot and any server-side caller use the
-- service role key) -- this is internal cooldown bookkeeping, not
-- user-facing data.
CREATE POLICY "bot_rate_limits_service_role" ON bot_rate_limits
  FOR ALL TO service_role USING (true) WITH CHECK (true);
