-- ============================================================
-- Migration 0054 — General Audit Events (SUOC Wave 2 / MSN-0210F Part 4)
-- Adds a general-purpose audit table alongside authority_audit_log
-- (migration 0053). authority_audit_log stays permission-check-specific
-- (officer/action/approved/captain_override columns don't fit a
-- "notification sent" or other non-permission event); this table takes
-- everything else via a category discriminator + free-form jsonb details,
-- per the MSN-0210F discovery finding that no general audit trail exists
-- anywhere in the codebase today.
-- Additive only — not yet written to by any production code path.
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_events (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    category    text        NOT NULL,           -- e.g. 'permission', 'approval', 'notification'
    actor       text        NOT NULL,           -- who/what performed the action
    action      text        NOT NULL,           -- what was done
    outcome     text        NOT NULL,           -- e.g. 'approved', 'denied', 'sent', 'failed'
    details     jsonb       NOT NULL DEFAULT '{}',
    mission_id  text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE audit_events IS
  'SUOC Wave 2: general-purpose audit trail (category/actor/action/outcome/details), '
  'distinct from authority_audit_log (migration 0053), which stays permission-check-specific. '
  'Populated via core/platform/audit_service.py record_audit_event(). Append-only.';

-- RLS: service_role bypasses; no public read/write (matches authority_audit_log/staff_autonomy_log)
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS audit_events_created_at_idx
    ON audit_events (created_at DESC);

CREATE INDEX IF NOT EXISTS audit_events_category_idx
    ON audit_events (category);

CREATE INDEX IF NOT EXISTS audit_events_actor_idx
    ON audit_events (actor);
