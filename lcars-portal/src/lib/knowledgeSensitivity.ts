// Command Memory sensitivity filtering (MSN-0333).
//
// The real authoritative enforcement point for the two RPC-based search
// functions (match_document_chunks, keyword_search_documents) is the SQL
// inside those functions themselves (migration 0063) -- it applies
// regardless of caller role, including service_role, which bypasses RLS.
//
// This module is for the smaller number of TS consumers that query
// knowledge_documents directly with the service-role key (ai-context.ts,
// the Knowledge Library memory routes) rather than through those RPCs --
// every such consumer should call filterGeneralAccess() rather than write
// its own exclusion, so the rule can't drift between them. Excludes
// exactly what the RPC functions exclude: sensitive and restricted
// documents, from GENERAL access (search/listing/export). A deliberate
// single-document lookup by ID is a different access pattern and does
// not go through this filter.

const GENERAL_EXCLUDED = new Set(['sensitive', 'restricted']);

export function isVisibleForGeneralAccess(metadata: Record<string, unknown> | null | undefined): boolean {
  const sensitivity = metadata?.sensitivity;
  return typeof sensitivity !== 'string' || !GENERAL_EXCLUDED.has(sensitivity);
}

export function filterGeneralAccess<T extends { metadata?: Record<string, unknown> | null }>(rows: T[]): T[] {
  return rows.filter((r) => isVisibleForGeneralAccess(r.metadata));
}
