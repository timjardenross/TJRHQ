-- ============================================================
-- Migration 0057 — Relationship Model Extension (SUOC Wave 3, Workstream D)
-- GENERALISES the existing ADR-022 knowledge graph (knowledge_nodes/
-- knowledge_edges, migration 0028) rather than building a second graph
-- system — confirmed by the Wave 3 discovery pass that no other
-- persisted relationship/graph store exists anywhere in the repo.
--
-- Adds the node types and relationship verbs needed for the platform
-- relationships requested in Wave 3 (Mission->Capability, Capability->
-- ADR, Capability->Pattern, Officer->Capability, Task->Event, Memory->
-- Confidence, Mission->Decision, Decision->Outcome, Outcome->Learning,
-- Learning->Pattern). Several of these already have a matching verb
-- (governed_by, produces, depends_on) — only 4 new verbs were actually
-- needed. Additive: every existing row, node_type, and relationship_type
-- remains valid; this only widens the allowed sets.
-- ============================================================

ALTER TABLE knowledge_nodes DROP CONSTRAINT IF EXISTS knowledge_nodes_type_chk;
ALTER TABLE knowledge_nodes ADD CONSTRAINT knowledge_nodes_type_chk CHECK (node_type IN (
    'principle', 'objective', 'initiative', 'mission', 'decision', 'adr', 'lesson',
    -- SUOC Wave 3 additions:
    'capability', 'pattern', 'officer', 'task', 'event', 'confidence', 'outcome', 'learning', 'memory'
));

ALTER TABLE knowledge_edges DROP CONSTRAINT IF EXISTS knowledge_edges_rel_type_chk;
ALTER TABLE knowledge_edges ADD CONSTRAINT knowledge_edges_rel_type_chk CHECK (relationship_type IN (
    'expresses', 'pursues', 'contains', 'produces', 'generates',
    'governed_by', 'informed_by', 'depends_on', 'supersedes',
    'validates', 'contradicts', 'references',
    -- SUOC Wave 3 additions: the 4 verbs not already covered by the above
    'implements',  -- Capability implements Pattern
    'owns',        -- Officer owns Capability
    'emits',       -- Task emits Event
    'informs'      -- Memory informs Confidence; Learning informs Pattern
));

COMMENT ON TABLE knowledge_nodes IS
  'ADR-022, extended SUOC Wave 3 (migration 0057): every navigable entity in the '
  'knowledge hierarchy AND the platform relationship graph. node_type now spans '
  'both the original governance hierarchy and platform runtime entities '
  '(capability/pattern/officer/task/event/confidence/outcome/learning/memory).';

COMMENT ON TABLE knowledge_edges IS
  'ADR-022, extended SUOC Wave 3 (migration 0057): typed directed edges, now '
  'covering platform-runtime relationships (Mission->Capability, Capability->ADR, '
  'Officer->Capability, Task->Event, etc.) in addition to the original governance '
  'hierarchy relationships.';
