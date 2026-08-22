-- 0158_capacity_checkins_sensory_regulation.sql
--
-- TJR Human Systems Workbench V3 (TJR_Human_Systems_Workbench_V3_Mission_
-- and_Change_Proposal.md), Mission 3 Part A — §10 "Sensory Regulation
-- Upgrade" and §11 "Natural Regulation Response". Both are additive,
-- optional, deep-check-tier layers on top of the existing quick-check-in
-- stimulation_state summary (0148) — that field is UNCHANGED, this
-- migration only adds a deeper, occasionally-answered layer on top of it,
-- same discipline 0153's own comment documents for its four fields (spec
-- §24: "must not become a 50-question autism/burnout assessment").
--
-- Deep-check tier, inserted after predictability (bc/pd), before
-- recovery_duration (rd) — see the companion capacity_today.py/app.py
-- change. All three columns nullable — every question here is itself
-- skippable, and "I don't know" / "not flagged" is a valid, first-class
-- answer, not a missing one (spec §24).
--
-- sensory_channels (V3 doc §10) — the "optional deeper Sensory Profile".
-- jsonb, not one column per channel, because most check-ins will only flag
-- 1-2 channels, not all 8 — same reasoning as burnout_profile.
-- contributing_signals (migration 0154): sparse by nature, and a fixed set
-- of 8 nullable text columns would mean 6+ NULLs on nearly every row for
-- no benefit (nothing downstream needs to filter/index on a single
-- channel in isolation yet). Keys are the V3 §10 channel list: auditory,
-- visual, touch, smell, movement, pressure, temperature,
-- environmental_complexity. Values are the V3 §10 response list:
-- reduce_avoid, neutral, seek_helpful, context_dependent, unknown. Example:
-- {"auditory": "reduce_avoid", "visual": "neutral"}. Written by
-- telegram-bots/capacitybot's per-channel deep-check loop (capacity_today.
-- write_deep_sensory_channel()) — one channel merged in per tap, not the
-- whole object at once, so a Captain can flag one channel and stop without
-- losing it if they don't finish the rest.
--
-- natural_regulation_response (V3 doc §11) — "what does my system seem to
-- want right now?", a single-select rather than jsonb/array because the
-- doc frames it as one dominant present-moment read, not a multi-select
-- inventory (unlike sensory_channels, which is deliberately allowed to
-- have several channels flagged at once). Canonical values match
-- telegram-bots/capacitybot/capacity_today.py's
-- NATURAL_REGULATION_CODE_TO_STATE: less_input, more_input, move,
-- fidget_repeat, quiet, stop_talking, be_alone,
-- connect_with_someone_safe, something_familiar, something_interesting,
-- pressure_sensory_comfort, get_thoughts_out, rest, dont_know.
--
-- suppressed_regulation_response (V3 doc §11) — "Am I stopping myself from
-- doing something that may help because it feels inappropriate,
-- inconvenient or noticeable?". Boolean, not an enum: the doc's own
-- framing is a single yes/no reflection question, and it "should feed
-- compensation-cost learning, not shame or correction" — nothing
-- downstream should ever render this column as a corrective flag on the
-- natural_regulation_response value next to it (V3 doc §3.6: harmless
-- regulation behaviours must not be automatically classified as symptoms
-- to suppress).

alter table public.capacity_checkins
  add column if not exists sensory_channels jsonb,
  add column if not exists natural_regulation_response text
    check (natural_regulation_response in (
      'less_input', 'more_input', 'move', 'fidget_repeat', 'quiet', 'stop_talking',
      'be_alone', 'connect_with_someone_safe', 'something_familiar', 'something_interesting',
      'pressure_sensory_comfort', 'get_thoughts_out', 'rest', 'dont_know')),
  add column if not exists suppressed_regulation_response boolean;
