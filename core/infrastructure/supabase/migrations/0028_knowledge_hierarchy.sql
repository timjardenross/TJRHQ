-- ============================================================
-- Migration 0028 — Knowledge Hierarchy Graph (ADR-022)
-- Adds knowledge_nodes and knowledge_edges for the hierarchical
-- knowledge navigation layer. Additive + idempotent.
-- Entities: principle(0) → objective(1) → initiative(2) → mission(3)
--           → decision(4) → adr(5) → lesson(6)
-- ============================================================

CREATE TABLE IF NOT EXISTS knowledge_nodes (
  node_id       text PRIMARY KEY,                 -- OBJ-001, INI-002, MSN-0053, ADR-009, LL-023
  node_type     text NOT NULL,                    -- principle|objective|initiative|mission|decision|adr|lesson
  level         integer NOT NULL                  -- 0–6 matching hierarchy depth
                  CHECK (level BETWEEN 0 AND 6),
  title         text NOT NULL,
  summary       text,
  status        text NOT NULL DEFAULT 'active',
  source_file   text,                             -- relative path to markdown source
  metadata      jsonb NOT NULL DEFAULT '{}',
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT knowledge_nodes_type_chk CHECK (node_type IN (
    'principle', 'objective', 'initiative', 'mission', 'decision', 'adr', 'lesson'
  ))
);

COMMENT ON TABLE knowledge_nodes IS
  'ADR-022: every navigable entity in the knowledge hierarchy. '
  'Source of truth: knowledge/hierarchy/Objectives.md, Initiatives.md, governance/ADR-*.md, '
  'knowledge/Lessons-Learned.md, knowledge/decisions/, Missions/Active/. '
  'Populated by core/knowledge-navigation/sync.py.';

CREATE TABLE IF NOT EXISTS knowledge_edges (
  edge_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id         text NOT NULL REFERENCES knowledge_nodes(node_id) ON DELETE CASCADE,
  target_id         text NOT NULL REFERENCES knowledge_nodes(node_id) ON DELETE CASCADE,
  relationship_type text NOT NULL,
  confidence        float NOT NULL DEFAULT 1.0
                      CHECK (confidence BETWEEN 0.0 AND 1.0),
  evidence          text,                         -- text snippet that revealed this relationship
  created_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT knowledge_edges_rel_type_chk CHECK (relationship_type IN (
    'expresses', 'pursues', 'contains', 'produces', 'generates',
    'governed_by', 'informed_by', 'depends_on', 'supersedes',
    'validates', 'contradicts', 'references'
  )),
  CONSTRAINT knowledge_edges_no_self_loop CHECK (source_id <> target_id),
  CONSTRAINT knowledge_edges_unique UNIQUE (source_id, target_id, relationship_type)
);

COMMENT ON TABLE knowledge_edges IS
  'ADR-022: typed directed edges between knowledge nodes. '
  'Relationship types: expresses|pursues|contains|produces|generates|governed_by|'
  'informed_by|depends_on|supersedes|validates|contradicts|references. '
  'confidence=1.0 for declared edges; <1.0 for auto-extracted edges.';

-- Traversal indexes
CREATE INDEX IF NOT EXISTS idx_knowledge_edges_source
  ON knowledge_edges (source_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_edges_target
  ON knowledge_edges (target_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_edges_rel_type
  ON knowledge_edges (relationship_type);

-- Filter indexes
CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_type
  ON knowledge_nodes (node_type);

CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_level
  ON knowledge_nodes (level);

CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_status
  ON knowledge_nodes (status);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION knowledge_nodes_set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS knowledge_nodes_updated_at ON knowledge_nodes;
CREATE TRIGGER knowledge_nodes_updated_at
  BEFORE UPDATE ON knowledge_nodes
  FOR EACH ROW EXECUTE FUNCTION knowledge_nodes_set_updated_at();

-- Reporting view: hierarchy summary
CREATE OR REPLACE VIEW knowledge_hierarchy_summary AS
SELECT
  node_type,
  level,
  status,
  count(*) AS node_count
FROM knowledge_nodes
GROUP BY node_type, level, status
ORDER BY level, node_type, status;

COMMENT ON VIEW knowledge_hierarchy_summary IS
  'ADR-022: node counts by type, level, and status for graph health monitoring.';

-- Reporting view: unmapped missions (missions with no initiative parent)
CREATE OR REPLACE VIEW knowledge_unmapped_missions AS
SELECT n.node_id, n.title, n.status
FROM knowledge_nodes n
WHERE n.node_type = 'mission'
  AND NOT EXISTS (
    SELECT 1 FROM knowledge_edges e
    WHERE e.target_id = n.node_id
      AND e.relationship_type = 'contains'
  )
ORDER BY n.node_id;

COMMENT ON VIEW knowledge_unmapped_missions IS
  'ADR-022: missions not yet assigned to an initiative. '
  'Use /map or tools/hierarchy/classify_missions.py to tag these.';
