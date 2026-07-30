import type { DocumentCategory, MemoryCategory } from './types';

/**
 * Category propagation — USS-TJR-MSN-0206J-2.
 *
 * knowledge_documents (Command Memory) never had a category at all before
 * this phase; only processing_documents (pre-approval staging) does, and
 * only for Personal Archive rows. Command Memory's 8-value taxonomy
 * (Health/Financial/Legal/Reference/Property/Operational Resilience/
 * Learning/Other) is deliberately different from the 10-value classifier
 * taxonomy on processing_documents (tuned for the AI classifier's output,
 * not for browsing a mixed governance + personal corpus) — this module is
 * the one place that bridges the two, mirroring migration 0048's SQL
 * backfill so a document approved today gets classified exactly the way
 * the 237 pre-existing rows were backfilled.
 */

const PROCESSING_CATEGORY_TO_MEMORY_CATEGORY: Partial<Record<DocumentCategory, MemoryCategory>> = {
  Health: 'Health',
  Financial: 'Financial',
  Legal: 'Legal',
  Identity: 'Legal',
  Reference: 'Reference',
  Property: 'Property',
  Correspondence: 'Other',
  Administrative: 'Other',
  Photo: 'Other',
  Other: 'Other',
};

// Repo governance document_type values (everything except 'Personal Archive').
const GOVERNANCE_DOCUMENT_TYPE_TO_MEMORY_CATEGORY: Record<string, MemoryCategory> = {
  ADR: 'Operational Resilience',
  Architecture: 'Operational Resilience',
  Mission: 'Operational Resilience',
  Crew: 'Reference',
  Capability: 'Reference',
  Specialist: 'Reference',
  'Knowledge Base': 'Learning',
  Unknown: 'Other',
};

/**
 * Assign a Command Memory category for a document being approved.
 * `processingCategory` should be the processing_documents classifier
 * category for Personal Archive approvals; ignored (and may be omitted)
 * for repo governance document types, which classify from `documentType`
 * alone.
 */
export function assignCategory(
  documentType: string,
  processingCategory: DocumentCategory | null | undefined,
): MemoryCategory {
  if (documentType !== 'Personal Archive') {
    return GOVERNANCE_DOCUMENT_TYPE_TO_MEMORY_CATEGORY[documentType] ?? 'Other';
  }
  return (processingCategory && PROCESSING_CATEGORY_TO_MEMORY_CATEGORY[processingCategory]) ?? 'Other';
}
