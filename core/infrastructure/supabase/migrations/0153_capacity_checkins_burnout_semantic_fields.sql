-- 0153_capacity_checkins_burnout_semantic_fields.sql
--
-- TJR Human Systems Workbench V3 (TJR_Human_Systems_Workbench_V3_Mission_
-- and_Change_Proposal.md), Mission 1 Part A — the doc's stated #1 priority
-- is elevating burnout/sustained-strain into a first-class TRAJECTORY
-- signal, distinct from the existing NOW signal. This migration adds the
-- four raw per-check-in fields the trajectory engine (core/health/
-- burnout_trajectory.py, migration 0154's burnout_profile table) reads to
-- derive that signal. It does NOT compute or store a trajectory itself —
-- that stays longitudinal/derived, in burnout_profile, never on a single
-- check-in row.
--
-- Deep-check tier, not quick-check-in tier — same discipline 0152's own
-- comment already documents for that migration's Sleep/Emotional/Social
-- split: the quick check-in (spec's 9-ish questions) must stay short (V3
-- doc §24: "must not become a 50-question autism/burnout assessment"), so
-- these four are asked only after "Go deeper" (telegram-bots/capacitybot/
-- capacity_today.py's deep-check flow, inserted between masking_present
-- and recovery_duration — see the companion capacity_today.py/app.py
-- change), same as load_category/recovery_duration/recovery_factors
-- already are. All four nullable — a deep check is optional, and every
-- option is itself skippable/"I don't know" per V3 doc §24 (each check
-- constraint below has an explicit not-sure/no-label value for exactly
-- that reason, not just column nullability).
--
-- user_burnout_framing (V3 doc §5.1 "User framing") — the user's own
-- self-identification, kept strictly separate from the system's derived
-- observation (burnout_profile.system_trajectory, migration 0154). The
-- system must never silently convert its own observation into this field
-- or vice versa (doc: "The system must never silently convert its
-- observation into a diagnosis").
--
-- compensation_type (V3 doc §6.4) — splits the existing single
-- compensation_load enum (amount only, 0148) into WHAT KIND of
-- compensation is happening. text[], not check-constrained to a fixed
-- list (unlike the single-select fields below) for the same reason
-- active_loads/identified_needs (0148) aren't: multi-select option
-- wording may evolve without a migration, this column is additive
-- context, and no downstream logic branches on an exhaustive value set —
-- the trajectory engine only counts array length/frequency. Canonical
-- values written by the bot (capacity_today.py's COMPENSATION_TYPE_VALUES):
-- suppressing_movement, suppressing_sensory_needs, performing_social,
-- forcing_speech, hiding_pain_fatigue, hiding_need_for_solitude,
-- pretending_to_understand, suppressing_need_for_routine.
--
-- body_signal_clarity (V3 doc §13) — explicitly NOT an interoception
-- deficit claim ("do not assume impaired interoception"), a neutral
-- self-report of how legible the user's own body signals feel right now.
--
-- predictability (V3 doc §12) — Predictability / Change Load, a
-- CONDITIONS-layer variable (V3 doc §4 Layer 2), not a rigid-routine
-- score.

alter table public.capacity_checkins
  add column if not exists user_burnout_framing text
    check (user_burnout_framing in (
      'identify_as_burnout', 'may_be_in_burnout', 'recovering_from_burnout', 'no_label', 'not_set')),
  add column if not exists compensation_type text[],
  add column if not exists body_signal_clarity text
    check (body_signal_clarity in ('clear', 'somewhat_clear', 'hard_to_interpret', 'no_idea')),
  add column if not exists predictability text
    check (predictability in ('clear_predictable', 'some_uncertainty', 'lots_changing', 'dont_know'));
