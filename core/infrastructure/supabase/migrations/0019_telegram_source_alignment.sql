-- ROS-001 v1.1 Sprint 6 — Telegram alignment
-- Adds 'telegram' as a valid source on health_daily_logs and health_events
-- so a future Telegram bot writes to the same tables as the Slack bot.

ALTER TABLE health_daily_logs
  DROP CONSTRAINT IF EXISTS health_daily_logs_source_check;

ALTER TABLE health_daily_logs
  ADD CONSTRAINT health_daily_logs_source_check
  CHECK (source = ANY (ARRAY['slack', 'telegram', 'manual', 'import']));

ALTER TABLE health_events
  DROP CONSTRAINT IF EXISTS health_events_source_check;

ALTER TABLE health_events
  ADD CONSTRAINT health_events_source_check
  CHECK (source = ANY (ARRAY['slack', 'telegram', 'manual', 'import']));
