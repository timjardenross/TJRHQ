// EOS Phase 2 Priority 1 — thin client for the Recommendation Engine bridge
// (api/recommendations/route.ts). Mirrors lib/decide.ts's fetchDecideCount():
// a simple, typed, no-business-logic wrapper - all ranking/scoring/health-
// gating/evidence-citation logic stays in core/coordination/
// recommendation_engine.py, reused as-is via the API route. This file only
// fetches and types the response; it is not wired into HomeScreen.tsx here -
// that integration is a separate, concurrent step.

export interface RecommendationItem {
  priority_rank: number;
  mission_id: string;
  title: string;
  reason: string;
  deadline_urgency: 'high' | 'medium' | 'low' | 'none';
  confidence: number;
  next_action: string;
  blockers: string[];
  health_constraint_note: string | null;
  due_date: string | null;
}

export interface RecommendationPackage {
  assembled_at: string;
  recommendations: RecommendationItem[];
  health_constraints_applied: boolean;
  total_active_missions: number;
}

/** Fetches the current recommendation package from the real Python engine
 * (via /api/recommendations). Returns null on any failure - callers degrade
 * to "not available" rather than a fabricated empty-but-successful package. */
export async function fetchRecommendations(): Promise<RecommendationPackage | null> {
  try {
    const resp = await fetch('/api/recommendations');
    if (!resp.ok) return null;
    const pkg = await resp.json();
    if (!pkg || typeof pkg !== 'object' || !Array.isArray(pkg.recommendations)) return null;
    return pkg as RecommendationPackage;
  } catch {
    return null;
  }
}
