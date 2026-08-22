-- 0157_capacity_interventions_evidence_metadata.sql
-- TJR Human Systems Workbench V3 — Mission 5. See
-- TJR_Human_Systems_Workbench_V3_Mission_and_Change_Proposal.md §16
-- "Evidence Metadata".
--
-- Additive only — capacity_interventions (0151) keeps its existing 30-row
-- seeded catalogue and every existing column untouched. This adds columns
-- to hold *general* evidence metadata (what research/guidance says about
-- an intervention) alongside the *personal* effectiveness data that
-- already lives in capacity_intervention_events. §16 is explicit these
-- two are never the same thing and must never be blended into one score
-- — general evidence tells you what's worth trying, personal outcome data
-- (capacity_intervention_events, unchanged by this migration) tells you
-- what has actually worked for this individual.

alter table public.capacity_interventions
  add column if not exists evidence_basis text,
  add column if not exists evidence_strength text
    check (evidence_strength in (
      'established_guideline_aligned', 'moderate', 'emerging',
      'lived_experience_informed', 'personal_only', 'unknown'))
    default 'unknown',
  add column if not exists evidence_source_type text,
  add column if not exists last_evidence_review date,
  add column if not exists context_tags text[];

comment on column public.capacity_interventions.evidence_basis is
  'Free-text summary of what general evidence/guidance says about this '
  'intervention (spec §16). Not a clinical claim — see evidence_strength '
  'for how much weight to put on it.';
comment on column public.capacity_interventions.evidence_strength is
  'How strong the general (non-personal) evidence is, per spec §16''s '
  'scale. Defaults to ''unknown'' — the honest default for a catalogue '
  'entry until someone has actually reviewed it, not a claim of '
  'validation. Never combine with personal effectiveness '
  '(capacity_intervention_events) into a single confidence number.';
comment on column public.capacity_interventions.evidence_source_type is
  'What kind of source evidence_basis draws on (e.g. clinical guideline, '
  'peer-reviewed study, lived-experience community consensus). Free text '
  '— not a controlled vocabulary, this is a personal single-user tool.';
comment on column public.capacity_interventions.last_evidence_review is
  'Date this intervention''s evidence fields were last reviewed by a '
  'human. Null until first reviewed.';
comment on column public.capacity_interventions.context_tags is
  'Free-form tags for filtering/grouping (e.g. sensory, executive, '
  'social) — separate from management_lever/target_states, which drive '
  'the recommendation engine (intervention_engine.py); these are '
  'descriptive only and not read by the ranking logic.';

-- Backfill: make the 30 existing seeded rows explicitly 'unknown' rather
-- than relying on the column default applying only to future inserts.
-- Redundant with the default above for any row that already picked it up,
-- but spec §27/§29 discipline is "never let missing evidence quietly read
-- as validated" — an explicit 'unknown' is the honest state, not a null
-- that some future query might misinterpret as "not yet checked" vs.
-- "checked, and there's nothing".
update public.capacity_interventions
  set evidence_strength = 'unknown'
  where evidence_strength is null;

-- Deliberately NOT seeding evidence_basis / evidence_source_type /
-- last_evidence_review / context_tags for the 30 existing catalogue rows
-- here. Populating "what the evidence says" for each of the 30 seeded
-- interventions is a human curation task (someone actually reviewing the
-- literature/guidance per intervention), not something to fabricate in a
-- migration. Those columns stay null for all existing rows until a human
-- does that review; evidence_strength stays 'unknown' for them until then,
-- which is exactly what keeps the UI from showing a confidence badge on
-- rows nobody has actually evaluated (see WhatHelpsMeCard.tsx).
