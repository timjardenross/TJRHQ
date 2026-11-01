-- 0218_mission5_evidence_domain_generalisation.sql
-- Mission 5 — Evidence & Adaptive Support.
--
-- Discovery (see knowledge/missions/USS-TJR-MSN-XXX-mission5-knowledge-record.md)
-- found capacity_interventions / capacity_intervention_events (0151, 0157,
-- 0202) already implement the canonical evidence model Mission 5 needs:
-- provenance-separated evidence (general evidence_strength vs personal
-- personal_causal_effect), causality-guarded confidence, non-punitive
-- unknown/pending defaults. Mission 5 generalises this ONE model across
-- domains rather than building a second evidence engine — per Captain
-- decision, capacity domain behaviour must not be destabilised.
--
-- Additive only. Existing 30-row capacity catalogue, existing columns,
-- and capacitybot's existing queries are untouched — every new column
-- defaults such that old rows/readers see exactly what they saw before.

-- ── domain scoping ───────────────────────────────────────────────────────
-- Lets the same two tables carry Ready Room execution-support evidence
-- alongside Capacity Bot's own, instead of a second parallel schema.
-- Extend the check constraint (not an enum) so future domains are another
-- additive migration, matching this repo's existing migration style.

alter table public.capacity_interventions
  add column if not exists domain text not null default 'capacity'
    check (domain in ('capacity', 'ready_room'));

alter table public.capacity_intervention_events
  add column if not exists domain text not null default 'capacity'
    check (domain in ('capacity', 'ready_room'));

comment on column public.capacity_interventions.domain is
  'Which support system this catalogue entry belongs to. ''capacity'' rows '
  'are Capacity Bot''s existing 30-code catalogue (unchanged). ''ready_room'' '
  'rows are Mission 4 execution-support interventions (UNSTICK ME, '
  'decompose-to-one-action, overload reduction, regulation) now '
  'participating in the same evidence model. Do not filter capacitybot '
  'queries by domain if they do not already — they were written before '
  'this column existed and correctly see only their own capacity rows '
  'today because ready_room rows are new inserts, not backfilled capacity '
  'data.';

-- ── generalised context capture ─────────────────────────────────────────
-- capacity_intervention_events'  *_before columns (capacity/pain/
-- stimulation/executive/compensation) are capacity-domain-specific and
-- stay exactly as-is — do not repurpose them for other domains, that
-- would silently misrepresent what was actually observed (spec §37:
-- canonical truth over speculative evidence). Non-capacity domains
-- instead write a structured context snapshot here; capacity domain rows
-- leave this null and keep using their typed columns unchanged.

alter table public.capacity_intervention_events
  add column if not exists context_snapshot jsonb,
  add column if not exists task_ref text;

comment on column public.capacity_intervention_events.context_snapshot is
  'Domain-agnostic context at intervention time, for domains whose '
  'context does not fit the capacity-specific *_before columns (e.g. '
  'ready_room: {"posture": "PROTECT", "capacity": "red", '
  '"attention_category": "..."}). Posture uses the live six-state '
  'runtime vocabulary (ENGAGE/STEADY/PROTECT/RECOVER/RESET/UNKNOWN) — '
  'never the three-state wording from an earlier mission brief draft. '
  'Null for capacity-domain rows, which keep using the typed columns.';
comment on column public.capacity_intervention_events.task_ref is
  'Free-text reference to the Ready Room task/item this event relates to '
  '(personal_tasks id or similar), when applicable. Null for capacity '
  'domain rows (checkin_id already serves that role there).';

-- source/outcome/would_use_again vocab already covers ready_room's needs
-- (outcome: better/same/worse/not_completed/unknown; would_use_again:
-- yes/maybe/no) — Mission 5 §12 explicitly maps HELPFUL/NOT HELPFUL/NOT
-- NOW onto exactly this shape (better~helpful, worse~not helpful,
-- not_completed/unknown~not now, never inferring "worse"/"no" from a
-- dismissed prompt). Extend `source` so Ready Room event writers have a
-- non-capacity value to use instead of overloading 'manual'.

alter table public.capacity_intervention_events
  drop constraint if exists capacity_intervention_events_source_check;
alter table public.capacity_intervention_events
  add constraint capacity_intervention_events_source_check
  check (source in ('capacity_q9', 'helpme', 'guide', 'manual', 'ready_room'));

-- checkin_id stays required-nullable (already nullable) and simply stays
-- null for ready_room rows, exactly as it already does for helpme/guide.

create index if not exists capacity_interventions_domain_idx
  on public.capacity_interventions (domain);
create index if not exists capacity_intervention_events_domain_idx
  on public.capacity_intervention_events (domain);

-- ── Captain correction / preference mechanism (spec §17, §20, §29) ─────
-- capacity_preferences (0151) has been an unused key/value stub since
-- creation — zero reads, zero writes, confirmed by Mission 5 discovery.
-- Zero live rows means restructuring it now is a safe additive change,
-- not a breaking one. This becomes the one canonical place an explicit
-- Captain correction ("stop suggesting body doubling") is recorded, read
-- by adaptive selection logic before historical evidence, across domains.

alter table public.capacity_preferences
  add column if not exists domain text not null default 'capacity'
    check (domain in ('capacity', 'ready_room')),
  add column if not exists item_code text,
  add column if not exists preference_state text
    check (preference_state in ('preferred', 'do_not_suggest')),
  add column if not exists note text,
  add column if not exists source text not null default 'captain_stated'
    check (source in ('captain_stated', 'inferred')),
  add column if not exists updated_by text not null default 'captain';

comment on table public.capacity_preferences is
  'Explicit Captain preference/correction store (spec §17). A row here is '
  'CAPTAIN-STATED evidence (spec §9) and outranks historical/observed '
  'evidence for the same (domain, item_code) when selecting support — '
  'see intervention_engine.py. source is always ''captain_stated'' for '
  'anything written from a direct Captain correction; ''inferred'' is '
  'reserved for a future platform-suggested default and must never be '
  'silently promoted to captain_stated (spec §9).';
comment on column public.capacity_preferences.item_code is
  'References capacity_interventions.intervention_id for a per-intervention '
  'preference. Null with only a note is allowed for a general '
  'domain-level correction that doesn''t target one specific intervention.';
comment on column public.capacity_preferences.preference_state is
  '''do_not_suggest'' stops an intervention being offered regardless of '
  'positive historical evidence (spec §17/§29 — explicit Captain intent '
  'outranks historical inference). ''preferred'' nudges ranking toward '
  'it. Absence of a row is not an implicit ''do_not_suggest'' — it means '
  'no correction has been made.';

create unique index if not exists capacity_preferences_domain_item_idx
  on public.capacity_preferences (domain, item_code)
  where item_code is not null;

-- ── Seed: Ready Room execution-support catalogue (domain='ready_room') ──
-- Mission 4's actual support surfaces, given canonical intervention
-- identity so events can reference them. Context filters use the live
-- six-state posture vocabulary where posture-specific, else '{}' (no
-- posture filter — offered regardless, per whatever Ready Room's own
-- logic already decides to surface it).

insert into public.capacity_interventions
  (intervention_id, domain, title, full_description, button_label,
   management_lever, target_states, capacity_allowed, stimulation_effect,
   pain_compatible, executive_effort, environment, requires_followup,
   evidence_strength)
values
  ('rr_unstick_me', 'ready_room', 'UNSTICK ME', 'Reduce a stalled task to one concrete next action.', 'Unstick me', 'reduce_load',
   '{cannot_start,overwhelmed}', '{green,orange,red}', 'neutral', true, 'low', '{anywhere}', true, 'unknown'),
  ('rr_decompose_one_action', 'ready_room', 'One-Action decomposition', 'Break a task down to a single next physical action, nav-free.', 'Break it down', 'reduce_load',
   '{cannot_start,overwhelmed}', '{green,orange,red}', 'neutral', true, 'low', '{anywhere}', true, 'unknown'),
  ('rr_overload_reduction', 'ready_room', 'Overload reduction sequence', 'Posture-aware sequence for "this feels like too much" — reduce visible scope.', 'This feels like too much', 'reduce_load',
   '{overwhelmed}', '{orange,red}', 'decrease', true, 'low', '{anywhere}', true, 'unknown'),
  ('rr_interruption_recovery', 'ready_room', 'Interruption recovery', 'Resume a stalled/interrupted task with a re-entry prompt (Pick Up Banner).', 'Pick up where I left off', 'redesign',
   '{cannot_start}', '{green,orange,red}', 'neutral', true, 'low', '{anywhere}', true, 'unknown')
on conflict (intervention_id) do nothing;

-- ── Retry/idempotency support for domain='ready_room' event writers ─────
-- Spec §31: a client-side double-click or network retry on the Ready Room
-- feedback POST (see lcars-portal /api/ready-room/support-events) must
-- never insert two rows for the same feedback submission and inflate
-- evidence strength. The route generates one client-side idempotency_key
-- per feedback prompt instance and stores it in context_snapshot; this
-- partial unique index turns a retried insert into a detectable conflict
-- (23505) the route resolves by returning the already-written row instead
-- of writing a second one. Partial on context_snapshot ? 'idempotency_key'
-- so it imposes nothing on capacity-domain rows, which never set that key.
create unique index if not exists capacity_intervention_events_idempotency_idx
  on public.capacity_intervention_events (((context_snapshot ->> 'idempotency_key')))
  where context_snapshot ? 'idempotency_key';
