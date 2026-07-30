import type { DocumentCategory, RetentionPolicy } from './types';

/**
 * Retention policy assignment automation — USS-TJR-MSN-0206D.
 *
 * Deterministic, category-driven classification applied once, at the
 * moment a document is approved into Command Memory (knowledge_documents).
 * No automatic deletion happens anywhere in this module or its caller —
 * expiry_date and review_due_date are informational nudges for the
 * Captain, not triggers. 'Archived' is deliberately excluded from this
 * table: it's the one retention_policy value only ever set by an explicit
 * Captain action (see the retention API route), never assigned here.
 */

interface PolicyRule {
  retention_policy: Exclude<RetentionPolicy, 'Archived'>;
  expiryYears: number | null; // null = never expires
  reviewYears: number;
}

const POLICY_BY_CATEGORY: Partial<Record<DocumentCategory, PolicyRule>> = {
  Identity: { retention_policy: 'Permanent', expiryYears: null, reviewYears: 5 },
  Legal: { retention_policy: 'Permanent', expiryYears: null, reviewYears: 5 },
  Property: { retention_policy: 'Permanent', expiryYears: null, reviewYears: 5 },
  Financial: { retention_policy: 'Long-Term', expiryYears: 7, reviewYears: 3 },
  Health: { retention_policy: 'Long-Term', expiryYears: 7, reviewYears: 3 },
  Reference: { retention_policy: 'Long-Term', expiryYears: null, reviewYears: 3 },
  Correspondence: { retention_policy: 'Temporary', expiryYears: 2, reviewYears: 1 },
  Administrative: { retention_policy: 'Temporary', expiryYears: 2, reviewYears: 1 },
  Photo: { retention_policy: 'Temporary', expiryYears: 5, reviewYears: 2 },
};

// Category missing/unrecognised (e.g. 'Other', or a metadata-only approval
// with no classifier category) — most conservative class, shortest review
// window, so it surfaces for reclassification sooner rather than later.
const DEFAULT_RULE: PolicyRule = { retention_policy: 'Expiring', expiryYears: 1, reviewYears: 0.5 };

// Repo governance content (ADR/Architecture/Crew/Mission/Capability/
// Knowledge Base/Specialist) has no natural expiry — operational knowledge
// this system relies on, not a personal file with a shelf life.
const GOVERNANCE_RULE: PolicyRule = { retention_policy: 'Permanent', expiryYears: null, reviewYears: 5 };

export interface RetentionAssignment {
  retention_policy: Exclude<RetentionPolicy, 'Archived'>;
  expiry_date: string | null;
  archive_status: 'active';
  review_due_date: string;
}

function addYears(from: Date, years: number): string {
  const d = new Date(from.getTime());
  const wholeYears = Math.floor(years);
  d.setFullYear(d.getFullYear() + wholeYears);
  if (years - wholeYears >= 0.5) d.setMonth(d.getMonth() + 6);
  return d.toISOString();
}

/**
 * Assign a retention policy for a document being approved into Command
 * Memory. `category` should be the processing_documents classifier
 * category for Personal Archive approvals, or omitted for repo governance
 * document types (ADR, Architecture, etc.), which always get the
 * Permanent governance rule regardless of category.
 */
export function assignRetentionPolicy(
  documentType: string,
  category: DocumentCategory | null | undefined,
  now: Date,
): RetentionAssignment {
  const rule = documentType !== 'Personal Archive'
    ? GOVERNANCE_RULE
    : (category && POLICY_BY_CATEGORY[category]) || DEFAULT_RULE;

  return {
    retention_policy: rule.retention_policy,
    expiry_date: rule.expiryYears === null ? null : addYears(now, rule.expiryYears),
    archive_status: 'active',
    review_due_date: addYears(now, rule.reviewYears),
  };
}
