-- Phase 1B: Surface health article sources in Intelligence Workbench
-- Extends health_insights to include source article references + metadata

ALTER TABLE health_insights
ADD COLUMN IF NOT EXISTS source_articles JSONB DEFAULT NULL,
ADD COLUMN IF NOT EXISTS committed_to_memory BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS committed_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;

-- Index for committed memory lookups
CREATE INDEX IF NOT EXISTS idx_health_insights_committed 
ON health_insights(committed_to_memory, created_at DESC);

-- Index for reviewed insights
CREATE INDEX IF NOT EXISTS idx_health_insights_reviewed 
ON health_insights(reviewed_at DESC) WHERE reviewed_at IS NOT NULL;

COMMENT ON COLUMN health_insights.source_articles IS 
'JSONB array of article references: [{title, url, summary, published_date, source_type}]';

COMMENT ON COLUMN health_insights.committed_to_memory IS 
'True if insight has been explicitly committed to memory by captain';

COMMENT ON COLUMN health_insights.committed_at IS 
'Timestamp when insight was committed to memory';

COMMENT ON COLUMN health_insights.reviewed_at IS 
'Timestamp when insight was reviewed (committed or discarded)';
