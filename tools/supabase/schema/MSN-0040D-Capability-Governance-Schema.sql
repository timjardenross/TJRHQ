-- USS-TJR-MSN-0040D: Unified Capability Governance Schema
-- Establishes single source of truth for capability tracking
-- Links governance (CAP-NNN), operations (P2-NNN), and runtime status
-- Apply manually in Supabase SQL editor or convert into a migration when ready.

-- Enable required extensions
create extension if not exists pgcrypto;

-- ============================================================================
-- CORE CAPABILITIES TABLE
-- Purpose: Single source of truth for all capabilities
-- Links governance (CAP-NNN), operational planning (P2-NNN), and runtime state
-- ============================================================================

create table if not exists capabilities (
  -- Identifiers
  id uuid primary key default gen_random_uuid(),
  governance_id text unique not null,  -- CAP-NNN (e.g., 'CAP-001')
  backlog_id text,                     -- P2-NNN (e.g., 'P2-006', optional for infrastructure)

  -- Core attributes
  title text not null,                 -- e.g., 'Mission Management'
  description text,                    -- Strategic objective from CAP definition
  category text,                       -- 'capability' | 'infrastructure' | 'enhancement'

  -- Governance authority (from CAP-NNN)
  primary_owner text,                  -- e.g., 'Chief of Staff'
  supporting_specialists text[],       -- ['Chief Engineer', 'Knowledge Officer']

  -- Lifecycle tracking
  status text not null default 'proposed',
    -- governance_status: proposed → approved → in_development → delivered → active → sunsetted
    -- valid values: 'proposed', 'approved', 'in_development', 'delivered', 'active', 'sunsetted'

  -- Runtime status (operational feedback)
  runtime_status text default 'inactive',
    -- valid values: 'inactive', 'in_development', 'deployed', 'active', 'degraded', 'offline'

  -- Strategic relationships
  supported_experiences text[],        -- ['EXP-001', 'EXP-004'] from CAP definition
  success_criteria text[],             -- Measurable success criteria from CAP definition

  -- Implementation tracking
  roadmap_phase text,                  -- 'Phase 2 Q1', 'Phase 2 Q2', etc.
  roadmap_priority text,               -- 'P1', 'P2', 'P3', etc.

  -- Metadata
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  created_by text default 'system',
  updated_by text default 'system',

  -- Audit trail
  notes text,                          -- Implementation notes, blockers, etc.
  metadata jsonb default '{}'::jsonb   -- Flexible extension point
);

-- Create indices for efficient querying
create index if not exists idx_capabilities_governance_id on capabilities (governance_id);
create index if not exists idx_capabilities_backlog_id on capabilities (backlog_id);
create index if not exists idx_capabilities_status on capabilities (status);
create index if not exists idx_capabilities_runtime_status on capabilities (runtime_status);
create index if not exists idx_capabilities_owner on capabilities (primary_owner);
create index if not exists idx_capabilities_created_at on capabilities (created_at desc);
create index if not exists idx_capabilities_updated_at on capabilities (updated_at desc);

-- ============================================================================
-- CAPABILITY DEPENDENCIES TABLE
-- Purpose: Track relationships between capabilities
-- Example: P2-007 (Voice Core) is infrastructure for P2-008 (Voice Captain's Log)
-- ============================================================================

create table if not exists capability_dependencies (
  id uuid primary key default gen_random_uuid(),
  source_cap_id uuid not null references capabilities(id) on delete cascade,
  -- source_cap: the capability that depends on something

  depends_on_cap_id uuid references capabilities(id) on delete cascade,
  -- depends_on_cap: the capability being depended on (if exists)

  depends_on_p2_id text,
  -- depends_on_p2: the P2 backlog item being depended on (for infrastructure)
  -- Example: P2-008 depends_on_p2_id = 'P2-007'

  dependency_type text not null,
  -- 'infrastructure' (requires infrastructure to be deployed first)
  -- 'sequential' (must be done after another capability)
  -- 'parallel' (can be done alongside)
  -- 'enhancement' (improves/extends existing capability)

  description text,
  -- Why this dependency exists

  created_at timestamptz default now(),

  constraint check_dependency_target
    check ((depends_on_cap_id is not null) or (depends_on_p2_id is not null))
);

create index if not exists idx_capability_dependencies_source
  on capability_dependencies (source_cap_id);
create index if not exists idx_capability_dependencies_target
  on capability_dependencies (depends_on_cap_id);

-- ============================================================================
-- CAPABILITY EVENTS TABLE
-- Purpose: Audit trail of capability status changes
-- Enables tracking when capabilities transition states, who updated them, why
-- ============================================================================

create table if not exists capability_events (
  id uuid primary key default gen_random_uuid(),
  capability_id uuid not null references capabilities(id) on delete cascade,
  governance_id text not null,  -- Denormalized for quick filtering

  event_type text not null,
  -- 'status_change' (governance status changed)
  -- 'runtime_update' (runtime status changed)
  -- 'owner_assigned' (owner assigned)
  -- 'blocker_added' (blocker identified)
  -- 'blocker_resolved' (blocker resolved)
  -- 'note_added' (implementation note added)

  old_value text,               -- Previous value (for status changes)
  new_value text,               -- New value (for status changes)

  description text,             -- Why the change was made

  created_at timestamptz default now(),
  created_by text not null,     -- User/system that triggered the event

  metadata jsonb default '{}'::jsonb
);

create index if not exists idx_capability_events_capability_id
  on capability_events (capability_id);
create index if not exists idx_capability_events_governance_id
  on capability_events (governance_id);
create index if not exists idx_capability_events_created_at
  on capability_events (created_at desc);
create index if not exists idx_capability_events_type
  on capability_events (event_type);

-- ============================================================================
-- CAPABILITY METRICS TABLE
-- Purpose: Track operational metrics for each capability
-- Example: CAP-001 mission creation count, CAP-003 knowledge retrieval latency
-- ============================================================================

create table if not exists capability_metrics (
  id uuid primary key default gen_random_uuid(),
  capability_id uuid not null references capabilities(id) on delete cascade,
  governance_id text not null,  -- Denormalized for quick filtering

  metric_name text not null,
  -- Examples: 'mission_count', 'retrieval_latency_ms', 'specialist_routing_accuracy'

  metric_value numeric not null,

  measurement_unit text,        -- 'count', 'ms', 'percent', etc.

  time_period text not null,    -- 'daily', 'weekly', 'monthly'
  period_start_date date not null,
  period_end_date date not null,

  recorded_at timestamptz default now(),
  recorded_by text default 'system',

  notes text,                   -- Context about the measurement
  metadata jsonb default '{}'::jsonb
);

create index if not exists idx_capability_metrics_capability_id
  on capability_metrics (capability_id);
create index if not exists idx_capability_metrics_governance_id
  on capability_metrics (governance_id);
create index if not exists idx_capability_metrics_metric_name
  on capability_metrics (metric_name);
create index if not exists idx_capability_metrics_period
  on capability_metrics (period_start_date, period_end_date);

-- ============================================================================
-- CAPABILITY INFRASTRUCTURE TABLE
-- Purpose: Track infrastructure items (not user-facing capabilities)
-- Examples: Tailscale, GitHub, Knowledge Workspace Definition
-- ============================================================================

create table if not exists capability_infrastructure (
  id uuid primary key default gen_random_uuid(),

  backlog_id text unique not null,    -- P2-NNN (e.g., 'P2-001')
  title text not null,                -- e.g., 'Tailscale Foundation'
  description text,
  category text not null,             -- 'networking', 'vcs', 'database', etc.

  status text not null default 'proposed',
  -- 'proposed', 'planned', 'in_progress', 'complete', 'deprecated'

  priority text,                      -- 'P1', 'P2', 'P3'

  roadmap_phase text,                 -- 'Phase 2 Q1', etc.

  owner text,
  supporting_teams text[],

  -- Capabilities enabled by this infrastructure
  enables_capabilities text[],        -- ['CAP-001', 'CAP-003']

  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  created_by text default 'system',
  updated_by text default 'system',

  notes text,
  metadata jsonb default '{}'::jsonb
);

create index if not exists idx_capability_infrastructure_backlog_id
  on capability_infrastructure (backlog_id);
create index if not exists idx_capability_infrastructure_status
  on capability_infrastructure (status);

-- ============================================================================
-- CAPABILITY EXPERIENCES LINKING TABLE
-- Purpose: Explicit linking between capabilities and experiences (EXP-NNN)
-- Enables querying: "Which experiences does this capability support?"
-- ============================================================================

create table if not exists capability_experiences (
  id uuid primary key default gen_random_uuid(),
  capability_id uuid not null references capabilities(id) on delete cascade,

  governance_id text not null,        -- CAP-NNN (e.g., 'CAP-001')
  experience_id text not null,        -- EXP-NNN (e.g., 'EXP-001')

  description text,                   -- How this capability supports the experience

  created_at timestamptz default now(),

  constraint uq_cap_exp
    unique (governance_id, experience_id)
);

create index if not exists idx_capability_experiences_governance_id
  on capability_experiences (governance_id);
create index if not exists idx_capability_experiences_experience_id
  on capability_experiences (experience_id);

-- ============================================================================
-- MATERIALIZED VIEW: CAPABILITY STATUS DASHBOARD
-- Purpose: Single query to get comprehensive capability status
-- Combines capabilities, infrastructure, dependencies, and metrics
-- ============================================================================

create or replace view v_capability_status as
select
  c.governance_id,
  c.backlog_id,
  c.title,
  c.category,
  c.status as governance_status,
  c.runtime_status,
  c.primary_owner,
  c.roadmap_phase,
  c.roadmap_priority,
  (select count(*) from capability_events where capability_id = c.id) as event_count,
  (select count(*) from capability_metrics where capability_id = c.id) as metric_count,
  c.updated_at,
  c.updated_by
from capabilities c
order by c.governance_id;

-- ============================================================================
-- INITIAL DATA: Capabilities (CAP-NNN)
-- Based on MSN-0040D mapping document
-- ============================================================================

insert into capabilities (
  governance_id, backlog_id, title, description, category,
  primary_owner, supporting_specialists, status, runtime_status,
  supported_experiences, roadmap_phase, roadmap_priority, created_by
) values
  ('CAP-001', 'P2-004', 'Mission Management',
   'Enable USS TJR to capture, manage, track, review and archive missions.',
   'capability', 'Chief of Staff',
   array['Chief Engineer', 'Knowledge Officer', 'QA & Test Officer'],
   'approved', 'active',
   array['EXP-001', 'EXP-004'], 'Phase 2 Q1-Q2', 'P1', 'system'),

  ('CAP-002', 'P2-009', 'Specialist Consultation',
   'Enable Captain TJR to access specialist expertise on demand.',
   'capability', 'Chief of Staff',
   array['Chief Engineer', 'Knowledge Officer', 'Coder Agent', 'QA & Test Officer', 'UX Design Officer'],
   'approved', 'active',
   array['EXP-002', 'EXP-003'], 'Phase 2 Q2', 'P1', 'system'),

  ('CAP-003', 'P2-005', 'Knowledge Retrieval',
   'Enable USS TJR to retrieve relevant knowledge quickly and accurately.',
   'capability', 'Knowledge Officer',
   array['Chief Engineer', 'Chief of Staff'],
   'approved', 'in_development',
   array['EXP-005', 'EXP-002'], 'Phase 2 Q1-Q2', 'P1', 'system'),

  ('CAP-004', 'P2-007', 'Voice Interaction',
   'Enable natural voice-based interaction with USS TJR.',
   'capability', 'Chief Engineer',
   array['UX Design Officer', 'Knowledge Officer'],
   'approved', 'inactive',
   array['EXP-007', 'EXP-008'], 'Phase 2 Q3', 'P2', 'system'),

  ('CAP-005', 'P2-006', 'Daily Command Brief',
   'Provide a daily operational briefing for Captain TJR.',
   'capability', 'Chief of Staff',
   array['Knowledge Officer'],
   'approved', 'in_development',
   array['EXP-006'], 'Phase 2 Q3', 'P2', 'system'),

  ('CAP-006', 'P2-009', 'Specialist Orchestration',
   'Coordinate multiple specialists to provide consolidated advice.',
   'capability', 'Chief of Staff',
   array['All Active Specialists'],
   'approved', 'active',
   array['EXP-009', 'EXP-002'], 'Phase 2 Q2', 'P1', 'system'),

  ('CAP-007', 'P2-005', 'Knowledge Synchronisation',
   'Maintain alignment between USS TJR knowledge systems.',
   'capability', 'Knowledge Officer',
   array['Chief Engineer'],
   'approved', 'in_development',
   array['EXP-005', 'EXP-006'], 'Phase 2 Q1-Q2', 'P1', 'system'),

  ('CAP-008', 'P2-004', 'Engineering Delivery',
   'Translate missions into engineering execution outcomes.',
   'capability', 'Chief Engineer',
   array['Coder Agent', 'QA & Test Officer', 'UX Design Officer'],
   'approved', 'in_development',
   array['EXP-001', 'EXP-004'], 'Phase 2 Q1-Q2', 'P1', 'system')
on conflict (governance_id) do nothing;

-- ============================================================================
-- INITIAL DATA: Infrastructure Items (P2-NNN)
-- Based on MSN-0040D mapping document
-- ============================================================================

insert into capability_infrastructure (
  backlog_id, title, description, category, status, priority,
  roadmap_phase, enables_capabilities, created_by
) values
  ('P2-001', 'Tailscale Foundation', 'Secure networking foundation for USS TJR cluster',
   'networking', 'in_progress', 'P1', 'Phase 2 Q1',
   array['CAP-001', 'CAP-002', 'CAP-003', 'CAP-006'], 'system'),

  ('P2-002', 'GitHub System of Record', 'Single authoritative version control system',
   'vcs', 'planned', 'P1', 'Phase 2 Q1',
   array['CAP-001', 'CAP-008'], 'system'),

  ('P2-003', 'Knowledge Workspace Definition', 'Organizational structure for knowledge sources',
   'workspace', 'planned', 'P1', 'Phase 2 Q1',
   array['CAP-003', 'CAP-007'], 'system')
on conflict (backlog_id) do nothing;

-- ============================================================================
-- CAPABILITY DEPENDENCIES (Initial Data)
-- ============================================================================

-- P2-008 Voice Captain's Log depends on P2-007 Voice Core Foundation
insert into capability_dependencies (source_cap_id, depends_on_p2_id, dependency_type, description)
select c.id, 'P2-007', 'infrastructure',
       'Voice Captain''s Log depends on Voice Core Foundation'
from capabilities c
where c.governance_id = 'CAP-004'
and not exists (
  select 1 from capability_dependencies cd
  where cd.depends_on_p2_id = 'P2-007'
)
on conflict do nothing;

-- ============================================================================
-- CAPABILITY-EXPERIENCE LINKING (Initial Data)
-- Establishes explicit links between CAP and EXP
-- ============================================================================

insert into capability_experiences (capability_id, governance_id, experience_id, description)
select
  c.id, 'CAP-001', 'EXP-001',
  'Mission Management capability supports Mission Creation experience'
from capabilities c where c.governance_id = 'CAP-001'
union all
select
  c.id, 'CAP-001', 'EXP-004',
  'Mission Management capability supports Mission Review and Closure experience'
from capabilities c where c.governance_id = 'CAP-001'
union all
select
  c.id, 'CAP-002', 'EXP-002',
  'Specialist Consultation capability supports Specialist Consultation experience'
from capabilities c where c.governance_id = 'CAP-002'
union all
select
  c.id, 'CAP-003', 'EXP-005',
  'Knowledge Retrieval capability supports Ask USS TJR experience'
from capabilities c where c.governance_id = 'CAP-003'
union all
select
  c.id, 'CAP-005', 'EXP-006',
  'Daily Command Brief capability supports Daily Command Brief experience'
from capabilities c where c.governance_id = 'CAP-005'
union all
select
  c.id, 'CAP-008', 'EXP-001',
  'Engineering Delivery capability supports Mission Creation experience'
from capabilities c where c.governance_id = 'CAP-008'
on conflict (governance_id, experience_id) do nothing;

-- ============================================================================
-- COMMENTS (Documentation)
-- ============================================================================

comment on table capabilities is
  'Single source of truth for capability governance, planning, and runtime status. Links CAP-NNN (governance), P2-NNN (planning), and runtime operations.';

comment on column capabilities.governance_id is
  'Authoritative governance identifier (CAP-NNN format). Links to CAP-001 through CAP-008 definitions.';

comment on column capabilities.backlog_id is
  'Operational backlog identifier (P2-NNN format). Links to P2-001 through P2-010 planning items.';

comment on column capabilities.status is
  'Governance lifecycle status: proposed → approved → in_development → delivered → active → sunsetted';

comment on column capabilities.runtime_status is
  'Operational status reflecting actual deployment state: inactive → in_development → deployed → active → degraded → offline';

comment on table capability_infrastructure is
  'Infrastructure items (P2-001 through P2-005) that enable capabilities but are not user-facing themselves.';

comment on table capability_events is
  'Audit trail of capability lifecycle events. Enables tracking when/who/why capabilities changed status.';

comment on table capability_metrics is
  'Operational metrics for capabilities. Example: mission creation rate, knowledge retrieval latency, specialist routing accuracy.';

-- ============================================================================
-- END SCHEMA
-- ============================================================================
-- This schema establishes USS TJR's single governance system:
-- - Capabilities table is single source of truth for capability status
-- - Governance IDs (CAP-NNN) link to strategic governance
-- - Backlog IDs (P2-NNN) link to operational planning
-- - Runtime status reflects actual deployment state
-- - Events/metrics provide audit trail and operational intelligence
--
-- MSN-0040D: Capability Registry Cleanup — APPROVED SOLUTION
-- Date: 2026-06-08
-- Authority: Captain TJR
