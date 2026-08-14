-- Exec-Assistant Tables Migration
-- Created: 2026-08-10
-- Purpose: Support proactive personal administrative assistant capabilities

-- ──────────────────────────────────────────────────────────────────────────
-- 1. Executive Context & Preferences
-- ──────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS exec_assistant_context (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  executive_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

  -- Type of context: 'preference' | 'priority' | 'relationship' | 'framework' | 'pattern'
  context_type TEXT NOT NULL,

  -- Key-value for structured storage
  key TEXT NOT NULL,
  value JSONB NOT NULL,

  -- Who set this: 'manual' (user), 'learned' (from feedback), 'inferred' (from patterns)
  source TEXT NOT NULL DEFAULT 'manual',

  -- Confidence score (0-1) for learned/inferred contexts
  confidence DECIMAL(3,2),

  -- When this was last updated
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

  -- Indexes for fast lookup
  CONSTRAINT unique_context_per_exec UNIQUE (executive_id, context_type, key)
);

CREATE INDEX idx_exec_assistant_context_exec_id ON exec_assistant_context(executive_id);
CREATE INDEX idx_exec_assistant_context_type ON exec_assistant_context(context_type);
CREATE INDEX idx_exec_assistant_context_source ON exec_assistant_context(source);

COMMENT ON TABLE exec_assistant_context IS 'Stores executive preferences, priorities, relationships, and learned patterns';


-- ──────────────────────────────────────────────────────────────────────────
-- 2. Commitments & Follow-ups Tracking
-- ──────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS exec_assistant_commitments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  executive_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

  -- What type of commitment: 'meeting' | 'deliverable' | 'follow-up' | 'decision' | 'review'
  commitment_type TEXT NOT NULL,

  -- Human-readable title and description
  title TEXT NOT NULL,
  description TEXT,

  -- Where this came from: 'telegram' | 'email' | 'calendar' | 'manual' | 'slack'
  source TEXT NOT NULL,
  source_id TEXT,  -- ID in the source system (email ID, message ID, etc)

  -- Status tracking
  status TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'in_progress' | 'completed' | 'overdue' | 'cancelled'

  -- Deadline and reminder
  due_date DATE,
  due_time TIME,
  reminded_at TIMESTAMP WITH TIME ZONE,

  -- Who this is assigned to: 'self' | specialist name | email
  assigned_to TEXT,
  assigned_at TIMESTAMP WITH TIME ZONE,

  -- Priority (1=highest, 5=lowest) or NULL for unranked
  priority INTEGER,

  -- Context: extracted details, stakeholders, success criteria
  context JSONB,

  -- Completion tracking
  completed_at TIMESTAMP WITH TIME ZONE,
  completion_notes TEXT,

  -- When this was created and last updated
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_exec_assistant_commitments_exec_id ON exec_assistant_commitments(executive_id);
CREATE INDEX idx_exec_assistant_commitments_status ON exec_assistant_commitments(status);
CREATE INDEX idx_exec_assistant_commitments_due_date ON exec_assistant_commitments(due_date);
CREATE INDEX idx_exec_assistant_commitments_assigned_to ON exec_assistant_commitments(assigned_to);
CREATE INDEX idx_exec_assistant_commitments_created ON exec_assistant_commitments(created_at DESC);

COMMENT ON TABLE exec_assistant_commitments IS 'Tracks all commitments, delegations, and follow-ups extracted from all sources';


-- ──────────────────────────────────────────────────────────────────────────
-- 3. Calendar Scheduling & Optimization
-- ──────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS exec_assistant_scheduling (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  executive_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

  -- Calendar event reference
  calendar_event_id TEXT NOT NULL,
  event_title TEXT NOT NULL,

  -- Current and proposed times
  current_time TIMESTAMP WITH TIME ZONE,
  proposed_time TIMESTAMP WITH TIME ZONE,

  -- Why we're suggesting this change
  reason_for_change TEXT NOT NULL,
  -- e.g., 'consolidation', 'conflict_resolution', 'focus_time_protection'
  change_type TEXT,

  -- How confident we are in this suggestion (0-1)
  confidence DECIMAL(3,2),

  -- Approval status: 'pending_approval' | 'approved' | 'rejected' | 'applied'
  status TEXT NOT NULL DEFAULT 'pending_approval',

  -- Details of approval/rejection
  approval_reason TEXT,
  approved_by TEXT,
  approved_at TIMESTAMP WITH TIME ZONE,

  -- When this suggestion was made
  suggested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_exec_assistant_scheduling_exec_id ON exec_assistant_scheduling(executive_id);
CREATE INDEX idx_exec_assistant_scheduling_status ON exec_assistant_scheduling(status);
CREATE INDEX idx_exec_assistant_scheduling_event_id ON exec_assistant_scheduling(calendar_event_id);

COMMENT ON TABLE exec_assistant_scheduling IS 'Tracks meeting optimization suggestions and approval status';


-- ──────────────────────────────────────────────────────────────────────────
-- 4. Proactive Alerts & Recommendations
-- ──────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS exec_assistant_alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  executive_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

  -- Type of alert
  alert_type TEXT NOT NULL,
  -- 'overload' | 'conflict' | 'relationship_gap' | 'pattern' | 'risk' | 'opportunity'

  -- Severity level
  severity TEXT NOT NULL,  -- 'low' | 'medium' | 'high'

  -- What to display
  title TEXT NOT NULL,
  description TEXT,

  -- What to do about it
  recommendation TEXT,

  -- Suggested action items (structured)
  action_items JSONB,

  -- Status: 'active' | 'acknowledged' | 'resolved' | 'dismissed'
  status TEXT NOT NULL DEFAULT 'active',

  -- When user acknowledged/resolved it
  acknowledged_at TIMESTAMP WITH TIME ZONE,
  resolved_at TIMESTAMP WITH TIME ZONE,

  -- Timeline
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_exec_assistant_alerts_exec_id ON exec_assistant_alerts(executive_id);
CREATE INDEX idx_exec_assistant_alerts_status ON exec_assistant_alerts(status);
CREATE INDEX idx_exec_assistant_alerts_severity ON exec_assistant_alerts(severity);
CREATE INDEX idx_exec_assistant_alerts_type ON exec_assistant_alerts(alert_type);
CREATE INDEX idx_exec_assistant_alerts_created ON exec_assistant_alerts(created_at DESC);

COMMENT ON TABLE exec_assistant_alerts IS 'Proactive alerts and recommendations for executive attention';


-- ──────────────────────────────────────────────────────────────────────────
-- 5. Generated Briefs & Summaries
-- ──────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS exec_assistant_briefs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  executive_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

  -- Type of brief
  brief_type TEXT NOT NULL,  -- 'daily' | 'weekly' | 'meeting_prep' | 'custom'

  -- Metadata
  title TEXT NOT NULL,
  subject_matter TEXT,  -- For meeting briefs: meeting title

  -- Content (structured as sections)
  content JSONB NOT NULL,
  sections JSONB,  -- Array of {section_title: string, content: string}

  -- Delivery
  generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  sent_at TIMESTAMP WITH TIME ZONE,
  delivery_channel TEXT,  -- 'telegram' | 'email' | 'dashboard'

  -- Feedback for learning
  rating INTEGER,  -- 1-5 scale
  feedback TEXT,

  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_exec_assistant_briefs_exec_id ON exec_assistant_briefs(executive_id);
CREATE INDEX idx_exec_assistant_briefs_type ON exec_assistant_briefs(brief_type);
CREATE INDEX idx_exec_assistant_briefs_created ON exec_assistant_briefs(created_at DESC);
CREATE INDEX idx_exec_assistant_briefs_sent ON exec_assistant_briefs(sent_at DESC);

COMMENT ON TABLE exec_assistant_briefs IS 'Generated executive briefs, summaries, and meeting prep documents';


-- ──────────────────────────────────────────────────────────────────────────
-- 6. Integration Sync Status
-- ──────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS exec_assistant_sync_status (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  executive_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

  -- What integration this is tracking
  integration_type TEXT NOT NULL,
  -- 'google_calendar' | 'gmail' | 'telegram' | 'slack' | 'supabase'

  -- Last sync details
  last_sync_at TIMESTAMP WITH TIME ZONE,
  last_sync_status TEXT,  -- 'success' | 'failed' | 'partial'
  last_sync_error TEXT,

  -- Cursor/checkpoint for incremental syncs
  sync_cursor TEXT,

  -- Configuration
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  config JSONB,

  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

  CONSTRAINT unique_sync_per_integration UNIQUE (executive_id, integration_type)
);

CREATE INDEX idx_exec_assistant_sync_status_exec_id ON exec_assistant_sync_status(executive_id);
CREATE INDEX idx_exec_assistant_sync_status_type ON exec_assistant_sync_status(integration_type);
CREATE INDEX idx_exec_assistant_sync_status_enabled ON exec_assistant_sync_status(enabled);

COMMENT ON TABLE exec_assistant_sync_status IS 'Tracks sync status for external integrations (calendar, email, etc)';


-- ──────────────────────────────────────────────────────────────────────────
-- 7. Enable Row-Level Security (RLS)
-- ──────────────────────────────────────────────────────────────────────────

-- Only executives can see their own data
ALTER TABLE exec_assistant_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE exec_assistant_commitments ENABLE ROW LEVEL SECURITY;
ALTER TABLE exec_assistant_scheduling ENABLE ROW LEVEL SECURITY;
ALTER TABLE exec_assistant_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE exec_assistant_briefs ENABLE ROW LEVEL SECURITY;
ALTER TABLE exec_assistant_sync_status ENABLE ROW LEVEL SECURITY;

-- RLS policies: users can only see their own executive data
CREATE POLICY exec_assistant_context_rls ON exec_assistant_context
  FOR SELECT USING (auth.uid() = executive_id);
CREATE POLICY exec_assistant_context_insert ON exec_assistant_context
  FOR INSERT WITH CHECK (auth.uid() = executive_id);
CREATE POLICY exec_assistant_context_update ON exec_assistant_context
  FOR UPDATE USING (auth.uid() = executive_id);

CREATE POLICY exec_assistant_commitments_rls ON exec_assistant_commitments
  FOR SELECT USING (auth.uid() = executive_id);
CREATE POLICY exec_assistant_commitments_insert ON exec_assistant_commitments
  FOR INSERT WITH CHECK (auth.uid() = executive_id);
CREATE POLICY exec_assistant_commitments_update ON exec_assistant_commitments
  FOR UPDATE USING (auth.uid() = executive_id);

CREATE POLICY exec_assistant_scheduling_rls ON exec_assistant_scheduling
  FOR SELECT USING (auth.uid() = executive_id);
CREATE POLICY exec_assistant_scheduling_insert ON exec_assistant_scheduling
  FOR INSERT WITH CHECK (auth.uid() = executive_id);
CREATE POLICY exec_assistant_scheduling_update ON exec_assistant_scheduling
  FOR UPDATE USING (auth.uid() = executive_id);

CREATE POLICY exec_assistant_alerts_rls ON exec_assistant_alerts
  FOR SELECT USING (auth.uid() = executive_id);
CREATE POLICY exec_assistant_alerts_insert ON exec_assistant_alerts
  FOR INSERT WITH CHECK (auth.uid() = executive_id);
CREATE POLICY exec_assistant_alerts_update ON exec_assistant_alerts
  FOR UPDATE USING (auth.uid() = executive_id);

CREATE POLICY exec_assistant_briefs_rls ON exec_assistant_briefs
  FOR SELECT USING (auth.uid() = executive_id);
CREATE POLICY exec_assistant_briefs_insert ON exec_assistant_briefs
  FOR INSERT WITH CHECK (auth.uid() = executive_id);
CREATE POLICY exec_assistant_briefs_update ON exec_assistant_briefs
  FOR UPDATE USING (auth.uid() = executive_id);

CREATE POLICY exec_assistant_sync_status_rls ON exec_assistant_sync_status
  FOR SELECT USING (auth.uid() = executive_id);
CREATE POLICY exec_assistant_sync_status_insert ON exec_assistant_sync_status
  FOR INSERT WITH CHECK (auth.uid() = executive_id);
CREATE POLICY exec_assistant_sync_status_update ON exec_assistant_sync_status
  FOR UPDATE USING (auth.uid() = executive_id);
