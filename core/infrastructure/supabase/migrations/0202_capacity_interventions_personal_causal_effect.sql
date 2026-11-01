-- 0202_capacity_interventions_personal_causal_effect.sql
--
-- Adds a personal, computed causal-effect estimate to
-- capacity_interventions — deliberately NOT evidence_strength/
-- evidence_basis (migration 0157). 0157 reserves those two columns for
-- *general* (literature/guideline) evidence and is explicit: "Never
-- combine with personal effectiveness (capacity_intervention_events) into
-- a single confidence number." A causal-impact estimate fitted against
-- this individual's own capacity_checkins history is exactly personal
-- effectiveness data, so it gets its own, clearly-named columns instead —
-- see telegram-bots/capacitybot/evidence_engine.py, which is the only
-- writer of these columns.
--
-- Additive only, same posture as 0157: existing rows, existing columns
-- and the 30-row seeded catalogue are untouched.

alter table public.capacity_interventions
  add column if not exists personal_causal_effect double precision,
  add column if not exists personal_causal_effect_ci_lower double precision,
  add column if not exists personal_causal_effect_ci_upper double precision,
  add column if not exists personal_causal_effect_p_value double precision,
  add column if not exists personal_causal_effect_summary text,
  add column if not exists personal_causal_effect_computed_at timestamptz;

comment on column public.capacity_interventions.personal_causal_effect is
  'Estimated shift (capacity zone-score points, same 0-100 scale as '
  'core.health.capacity_score) in this individual''s own capacity_checkins '
  'history coinciding with this intervention''s first use, from a '
  'tfcausalimpact (Bayesian structural time-series) fit. Computed by '
  'evidence_engine.py. NOT the same thing as evidence_strength (0157) — '
  'that column is general/literature evidence and must never be set from '
  'this personal estimate, per 0157''s own comment.';
comment on column public.capacity_interventions.personal_causal_effect_ci_lower is
  'Lower bound of the 95% credible interval for personal_causal_effect.';
comment on column public.capacity_interventions.personal_causal_effect_ci_upper is
  'Upper bound of the 95% credible interval for personal_causal_effect.';
comment on column public.capacity_interventions.personal_causal_effect_p_value is
  'Posterior tail-area probability from the CausalImpact fit — smaller '
  'means the estimated effect is less likely to be noise.';
comment on column public.capacity_interventions.personal_causal_effect_summary is
  'Human-readable one-paragraph rendering of the estimate above, including '
  'the observational-not-experimental caveat, as shown to the Captain.';
comment on column public.capacity_interventions.personal_causal_effect_computed_at is
  'When evidence_engine.py last (re)computed these columns for this '
  'intervention. Null until the intervention has enough pre/post check-in '
  'history (evidence_engine.MIN_PRE_DAYS / MIN_POST_DAYS) to estimate at all.';
