-- Migration 0061 — core_events: generic structured metrics bag
-- MSN-0328 Wave 2: Captain-facing presentation layers (Slack's /brief in
-- particular) render richly structured per-domain detail today (capacity
-- bands, delivery risk counts/constraints, ORI trend, strategic objective
-- progress) that a free-text `reason`/`recommended_action` alone can't
-- carry without lossy prose-parsing. Rather than inventing new top-level
-- CaptainBriefDocument sections (a redesign this mission's charter
-- explicitly rules out), domains attach whatever structured detail they
-- have as a generic JSONB bag; presentation layers read known keys where
-- present and fall back to reason/recommended_action where absent.
-- Additive only, mirrors migration 0059's precedent (adding
-- time_sensitivity to this same table after the fact).

ALTER TABLE core_events
  ADD COLUMN IF NOT EXISTS metrics jsonb NOT NULL DEFAULT '{}';

COMMENT ON COLUMN core_events.metrics IS
  'Optional structured detail (counts, scores, bands) a domain attaches '
  'at emission time, e.g. {"high_risk_count": 3, "open_count": 12}. '
  'Absent/empty is normal, not an error -- not every domain has structured '
  'detail worth attaching.';
