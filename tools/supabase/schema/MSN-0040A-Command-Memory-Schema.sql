-- ============================================================================
-- MSN-0040A — Command Memory MVP — Supabase Schema + Seed
-- ============================================================================
-- Mission:  USS-TJR-MSN-0040A (Command Memory MVP)
-- Scope:    Supabase-only. No embeddings, vector DB, RAG, or RLS (MVP scope).
-- Authority: Architecture Team
--
-- This file is the in-repo source of truth for the four Command Memory tables.
-- The tables are ALREADY DEPLOYED in the Supabase project (verified live). This
-- script is idempotent (IF NOT EXISTS) so it can recreate the schema from
-- scratch for rollback/restore or a fresh environment.
--
-- Apply via the Supabase SQL Editor or psql. The application layer
-- (slack-bot/command_memory_integration.py) talks to these tables over the
-- PostgREST REST API and CANNOT run this DDL itself.
--
-- Column set matches the MUST-HAVE (MVP) data model in MSN-0040A-DATA-MODEL.md.
-- FUTURE fields (priority, blocked_reason, depends_on, impact_area, cost_monthly,
-- etc.) are intentionally omitted until requirements prove necessity.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Table 1: missions
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS missions (
  id          TEXT PRIMARY KEY,                 -- canonical mission ID (e.g. USS-TJR-MSN-0040 or M-YYYYMMDD-HHMMSS)
  title       VARCHAR(255) NOT NULL,
  created_by  VARCHAR(50)  NOT NULL,            -- Slack user ID
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  -- MSN-0051 / Captain decision D-008: CANONICAL mission lifecycle (ADR-0001 /
  -- MSN-ENFORCE-001 7-state backbone + operational states Blocked, Archived).
  -- Migration 0013: 'Idea' added as dormant pre-triage capture state (assigned by
  -- /mission-capture). Ideas are excluded from the Number One work queue until
  -- promoted to 'Designed' by the Captain.
  -- TEXT (not VARCHAR(20)) because 'Awaiting Number One Review' exceeds 20 chars (matches live schema).
  status      TEXT         NOT NULL
              CHECK (status IN ('Idea','Designed','Implemented','Tested','Awaiting Number One Review','Validated','Awaiting XO Approval','Closed','Blocked','Archived')),
  owner       VARCHAR(50)  NOT NULL,
  updated_at  TIMESTAMPTZ  DEFAULT NOW(),
  updated_by  VARCHAR(50),
  description TEXT                                  -- LLM-generated capture body (migration 0013)
);

CREATE INDEX IF NOT EXISTS idx_missions_status     ON missions(status);
CREATE INDEX IF NOT EXISTS idx_missions_owner      ON missions(owner);
CREATE INDEX IF NOT EXISTS idx_missions_created_at ON missions(created_at DESC);

-- ----------------------------------------------------------------------------
-- Table 2: decisions
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS decisions (
  id           TEXT PRIMARY KEY,                -- DEC-YYYYMMDD-HHMMSS
  statement    VARCHAR(500) NOT NULL,           -- "We will X" / "We will not X" (immutable)
  rationale    TEXT         NOT NULL,           -- why this decision (may be empty string in MVP)
  created_by   VARCHAR(50)  NOT NULL,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  owner        VARCHAR(50)  NOT NULL,           -- decision authority
  status       VARCHAR(20)  NOT NULL
               CHECK (status IN ('Active','Superseded','Archived')),
  alternatives JSON,                            -- [{ "name": ..., "assessment": ... }, ...]
  updated_at   TIMESTAMPTZ  DEFAULT NOW(),
  updated_by   VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_decisions_status     ON decisions(status);
CREATE INDEX IF NOT EXISTS idx_decisions_created_at ON decisions(created_at DESC);

-- ----------------------------------------------------------------------------
-- Table 3: capabilities
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS capabilities (
  id          TEXT PRIMARY KEY,                 -- CAP-YYYYMMDD-HHMMSS or CAP-YYYY-NNN
  name        VARCHAR(255) NOT NULL,
  purpose     TEXT         NOT NULL,
  owner       VARCHAR(50)  NOT NULL,
  status      VARCHAR(20)  NOT NULL
              CHECK (status IN ('Planning','Building','Testing','Operational','Deprecated')),
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ  DEFAULT NOW(),
  updated_by  VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_capabilities_status ON capabilities(status);
CREATE INDEX IF NOT EXISTS idx_capabilities_owner  ON capabilities(owner);

-- ----------------------------------------------------------------------------
-- Table 4: architecture_records
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS architecture_records (
  id                 TEXT PRIMARY KEY,          -- ADR-YYYYMMDD-HHMMSS
  title              VARCHAR(255) NOT NULL,
  problem_statement  TEXT         NOT NULL,
  decision_summary   TEXT         NOT NULL,
  recommended_option VARCHAR(100) NOT NULL,
  decision_authority VARCHAR(50)  NOT NULL,
  decision_date      TIMESTAMPTZ  NOT NULL,
  status             VARCHAR(20)  NOT NULL
                     CHECK (status IN ('Active','Superseded','Archived')),
  alternatives       JSON,                      -- [{ "name": ..., "assessment": ... }, ...]
  created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ  DEFAULT NOW(),
  updated_by         VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_arch_status        ON architecture_records(status);
CREATE INDEX IF NOT EXISTS idx_arch_decision_date ON architecture_records(decision_date DESC);

-- ============================================================================
-- Rollback (MSN-0040A-MIGRATION-PLAN.md). Append-only model recovers cleanly.
-- ============================================================================
-- DROP TABLE IF EXISTS missions CASCADE;
-- DROP TABLE IF EXISTS decisions CASCADE;
-- DROP TABLE IF EXISTS capabilities CASCADE;
-- DROP TABLE IF EXISTS architecture_records CASCADE;
