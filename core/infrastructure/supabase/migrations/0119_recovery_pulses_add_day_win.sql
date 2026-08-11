-- 0119_recovery_pulses_add_day_win.sql
--
-- Captain-approved Recovery Pulse question-set redesign, 2026-08-10
-- (see .claude/skills/bot-reviews/fixes-2026-08-09/recovery-pulse-redesign-proposal.md,
-- §4 + §5 item 1). Part of the time-of-day-asymmetric question flow: the
-- evening pulse's 3rd tap is replaced with a reflective close-out question
-- ("One thing that went okay today?") instead of repeating body_signals.
-- This is new content with no existing column to reuse — additive, nullable,
-- no backfill required. Only ever populated by evening pulses; morning and
-- midday rows leave it NULL by design (they don't ask this question).

ALTER TABLE public.recovery_pulses
  ADD COLUMN day_win text
    CHECK (day_win IN ('something_did', 'nothing_much', 'rough_day'));

COMMENT ON COLUMN public.recovery_pulses.day_win IS
  'Evening-only reflective close-out answer to "One thing that went okay today?" '
  '(something_did | nothing_much | rough_day). Added 2026-08-10 as part of the '
  'time-of-day-asymmetric Recovery Pulse redesign — replaces a 3rd-tap repeat of '
  'body_signals on evening pulses only. NULL for morning/midday rows by design, '
  'not a data gap. See recovery-pulse-redesign-proposal.md.';
