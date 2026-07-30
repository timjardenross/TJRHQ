-- ============================================================
-- Migration 0053 — Authority Audit Log (SUOC Wave 1 / MSN-0210E)
-- Gives core/governance/authority_validator.py's audit_authority_action()
-- a dedicated, structured record instead of writing into the `decisions`
-- table (which by this point had 5 distinct, unrelated consumers layered
-- onto it — see reports/USS-TJR-MSN-0210-SUOC-Transition-Architecture.md
-- §4/§16). This is the first concrete instance of the "Audit" platform
-- service that dossier calls for; not a general-purpose audit trail for
-- every subsystem yet, just the one real call site that existed.
-- ============================================================

CREATE TABLE IF NOT EXISTS authority_audit_log (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    officer           text        NOT NULL,           -- manifest key, e.g. 'engineering', 'xo'
    action            text        NOT NULL,           -- action string checked against the manifest
    approved          boolean     NOT NULL,
    reason            text,                           -- why approved/denied (fail-open note, disallow reason, etc.)
    mission_id        text,                            -- optional mission context
    captain_override  boolean     NOT NULL DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE authority_audit_log IS
  'SUOC Wave 1: structured audit trail for core/governance/authority_validator.py '
  'authority checks. Replaces writing authority audit records into the decisions '
  'table. Append-only — no updates or deletes expected.';

-- RLS: service_role bypasses; no public read/write (matches staff_autonomy_log convention)
ALTER TABLE authority_audit_log ENABLE ROW LEVEL SECURITY;

-- Chronological feed (dashboard/review queries)
CREATE INDEX IF NOT EXISTS authority_audit_log_created_at_idx
    ON authority_audit_log (created_at DESC);

-- Filter by officer
CREATE INDEX IF NOT EXISTS authority_audit_log_officer_idx
    ON authority_audit_log (officer);

-- Filter by approved/denied (surfacing denials quickly)
CREATE INDEX IF NOT EXISTS authority_audit_log_approved_idx
    ON authority_audit_log (approved);
