-- Seed data for llm_cost_governance (Issue 21)
-- Initializes cost control thresholds for different LLM task types.
-- Run this after migration 0085.

-- Signal-scoring calls (Issue 14): ~50 signals/day during daily batch
-- Mistral 7B: ~$0.0001 per call, so 50 * $0.0001 = $0.005/day
-- Gemini: ~$0.001 per call, so 50 * $0.001 = $0.05/day
-- Set daily limit to $0.50 (buffer for extended days)
insert into llm_cost_governance (
  task_type,
  daily_call_limit,
  daily_cost_limit_usd,
  throttle_on_exceed,
  alert_at_percent,
  enabled,
  notes
) values (
  'signal-scoring',
  500,                    -- ~10x normal daily volume
  0.50,                   -- $0.50/day ceiling
  'fall_back_to_heuristic',
  80,
  true,
  'Issue 14 shadow-mode scoring. Falls back to heuristic if exceeded.'
)
on conflict (task_type) do update
set (daily_call_limit, daily_cost_limit_usd, throttle_on_exceed, alert_at_percent, enabled, updated_at)
  = (500, 0.50, 'fall_back_to_heuristic', 80, true, now());

-- Brief-synthesis calls (future): ~1 brief every 2 weeks
-- Much more expensive due to longer context.
-- Set to 10 calls/day (buffer), $2.00/day ceiling
insert into llm_cost_governance (
  task_type,
  daily_call_limit,
  daily_cost_limit_usd,
  throttle_on_exceed,
  alert_at_percent,
  enabled,
  notes
) values (
  'brief-synthesis',
  10,
  2.00,
  'alert',
  80,
  true,
  'Brief narrative synthesis. Alerts but does not block on exceed.'
)
on conflict (task_type) do update
set (daily_call_limit, daily_cost_limit_usd, throttle_on_exceed, alert_at_percent, enabled, updated_at)
  = (10, 2.00, 'alert', 80, true, now());

-- Health-mission correlation synthesis (Issue 18): 1x per day
-- Single structured call, relatively cheap.
-- Set to 5 calls/day (buffer), $0.10/day ceiling
insert into llm_cost_governance (
  task_type,
  daily_call_limit,
  daily_cost_limit_usd,
  throttle_on_exceed,
  alert_at_percent,
  enabled,
  notes
) values (
  'correlation-synthesis',
  5,
  0.10,
  'alert',
  80,
  true,
  'Health-mission correlation LLM synthesis (Issue 18).'
)
on conflict (task_type) do update
set (daily_call_limit, daily_cost_limit_usd, throttle_on_exceed, alert_at_percent, enabled, updated_at)
  = (5, 0.10, 'alert', 80, true, now());
