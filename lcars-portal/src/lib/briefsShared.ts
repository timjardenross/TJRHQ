// Briefs canonical uplift (BRIEFS_CANONICAL_UPLIFT.md) — shared types and
// the one content-selection helper Latest and the detail page both use, so
// they can't drift on what counts as "what matters" for a given brief.
// Mirrors intelligence/brief/render.py's build_morning_intelligence_view()
// on the Python side — same fields, same "nothing here is invented, only
// selected from the stored brief" contract.

export type ApprovalStatus = 'IN_REVIEW' | 'QA_PASSED' | 'PUBLISHED';

export interface BriefTopEvent {
  event_id?: string;
  title: string;
  location?: string;
  event_type?: string;
  risk_rating: string | null;
  summary?: string;
  operational_impact?: string;
  so_what?: string | null;
  status?: string;
  source_name?: string;
  canonical_url?: string | null;
  rank_score?: number;
}

export interface BriefComparison {
  new: { title: string; risk_rating?: string | null }[];
  escalated: { title: string; risk_rating?: string | null; prior_risk_rating?: string | null }[];
  improved: { title: string; risk_rating?: string | null; prior_risk_rating?: string | null }[];
  unchanged_but_material: { title: string; risk_rating?: string | null }[];
  no_longer_material: { title: string; risk_rating?: string | null }[];
}

export interface BriefCoverage {
  expected?: number;
  completed?: number;
  failed?: number;
  stale?: number;
  missing_sources?: string[];
  degraded?: boolean;
  cutoff_reached?: boolean;
  collection_status?: string;
  collection_checked_at?: string | null;
  latest_included_at?: string | null;
  morning_cycle_id?: string;
  reason?: string | null;
}

export interface BriefDomainBucket {
  label: string;
  count: number;
  worst_risk: string;
  events: { title: string; risk_rating: string | null }[];
}

// The list-view row shape (/api/briefs) — a subset of the full detail shape.
export interface BriefListItem {
  brief_id: string;
  generated_at: string;
  published_at: string | null;
  period_start: string | null;
  period_end: string | null;
  overall_risk: string | null;
  approval_status: ApprovalStatus | null;
  executive_snapshot: string | null;
  bottom_line?: string | null;
  morning_cycle_id?: string | null;
  top_events?: BriefTopEvent[] | null;
  comparison?: BriefComparison | null;
  coverage?: BriefCoverage | null;
  domain_picture?: Record<string, BriefDomainBucket> | null;
  known_unknowns?: string[] | null;
  forward_watch?: unknown;
}

export interface BriefDetail extends BriefListItem {
  cps230_implications?: unknown;
  emerging_themes?: unknown;
  signal_ids?: string[] | null;
  approval_audit?: Record<string, { status?: string; approved_by?: string }> | null;
}

export interface MorningIntelligenceView {
  hasBrief: boolean;
  overallRisk: string | null;
  executiveRead: string | null;
  whatMatters: { title: string; soWhat: string | null; riskRating: string | null }[];
  changed: { new: string[]; escalated: string[]; improved: string[] } | null;
  watch: string[];
  coverageNote: string | null;
  coverageDegraded: boolean;
}

/** Same selection intelligence/brief/render.py's build_morning_intelligence_view()
 * makes on the Python side — nothing here decides posture/what-matters on
 * its own, it only reads what the canonical brief already states. */
export function buildMorningIntelligenceView(
  brief: BriefListItem | null | undefined,
  maxItems = 3,
): MorningIntelligenceView {
  if (!brief) {
    return {
      hasBrief: false,
      overallRisk: null,
      executiveRead: null,
      whatMatters: [],
      changed: null,
      watch: [],
      coverageNote: null,
      coverageDegraded: false,
    };
  }

  const top = (brief.top_events ?? []).slice(0, maxItems);
  const whatMatters = top.map((e) => ({
    title: e.title,
    soWhat: e.so_what ?? null,
    riskRating: e.risk_rating,
  }));

  const comparison = brief.comparison ?? null;
  let changed: MorningIntelligenceView['changed'] = null;
  if (comparison) {
    const next = {
      new: (comparison.new ?? []).slice(0, 3).map((i) => i.title),
      escalated: (comparison.escalated ?? []).slice(0, 3).map((i) => i.title),
      improved: (comparison.improved ?? []).slice(0, 3).map((i) => i.title),
    };
    if (next.new.length || next.escalated.length || next.improved.length) changed = next;
  }

  const coverage = brief.coverage ?? {};
  const coverageDegraded = Boolean(coverage.degraded);
  let coverageNote: string | null = null;
  if (coverageDegraded) {
    const missing = coverage.missing_sources ?? [];
    if (missing.length === 1) {
      coverageNote = 'One intelligence source was unavailable during this morning collection cycle.';
    } else if (missing.length > 1) {
      coverageNote = `${missing.length} intelligence sources were unavailable during this morning collection cycle.`;
    } else {
      coverageNote = coverage.reason ?? "This morning's collection cycle was degraded.";
    }
  }

  const watchRaw = brief.forward_watch;
  const watch: string[] = Array.isArray(watchRaw)
    ? watchRaw.slice(0, 5).map((w) => (typeof w === 'string' ? w : JSON.stringify(w)))
    : [];

  return {
    hasBrief: true,
    overallRisk: brief.overall_risk ?? 'UNKNOWN',
    executiveRead: brief.executive_snapshot ?? brief.bottom_line ?? null,
    whatMatters,
    changed,
    watch,
    coverageNote,
    coverageDegraded,
  };
}

export function isToday(dateStr: string | null | undefined): boolean {
  if (!dateStr) return false;
  const d = new Date(dateStr);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}
