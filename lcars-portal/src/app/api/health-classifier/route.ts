/**
 * Health Content Classifier API
 *
 * Phase 1C: Exposes health classifier for Intelligence Workbench
 *
 * Endpoints:
 * - GET /api/health-classifier/validate — Validate threshold on real data
 * - GET /api/health-classifier/audit-log — Get suppressed signals audit trail
 * - POST /api/health-classifier/score — Score individual health insight
 * - GET /api/health-classifier/mappings — Get wellness→pillar mappings
 */

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';

// Classifier enums
enum ContentPillar {
  OPERATIONAL_RESILIENCE = 'Operational Resilience',
  HUMAN_PERFORMANCE = 'Human Performance',
  WELLNESS_SUSTAINABLE = 'Wellness & Sustainable Performance',
  PERSONAL_OS = 'Personal Operating Systems',
  AI_AUGMENTED_LEADERSHIP = 'AI-Augmented Leadership',
  FUTURE_OF_WORK = 'Future of Work',
  BUSINESS_INNOVATION = 'Business Innovation',
  EXECUTION_EXCELLENCE = 'Execution Excellence',
}

enum WellnessCategory {
  TEAM_WELLNESS = 'Team Wellness',
  MENTAL_HEALTH = 'Mental Health Support',
  MANAGER_TRAINING = 'Manager Training',
  CULTURE_BELONGING = 'Culture & Belonging',
  RESILIENCE_PROGRAMS = 'Resilience Programs',
  WORK_FLEXIBILITY = 'Work Flexibility',
  BURNOUT_PREVENTION = 'Burnout Prevention',
  PHYSICAL_WELLNESS = 'Physical Wellness',
  PRODUCTIVITY_OPTIMIZATION = 'Productivity Optimization',
}

// Pillar mappings (Phase 1C locked)
const PILLAR_MAPPINGS: Record<WellnessCategory, any> = {
  [WellnessCategory.TEAM_WELLNESS]: {
    primary: ContentPillar.WELLNESS_SUSTAINABLE,
    secondary: ContentPillar.HUMAN_PERFORMANCE,
    rationale: 'Individual wellbeing + performance impact',
  },
  [WellnessCategory.MENTAL_HEALTH]: {
    primary: ContentPillar.WELLNESS_SUSTAINABLE,
    secondary: null,
    rationale: 'Mental health is primary wellness concern',
    deferred_to_phase2: true,
    phase2_reason: 'Sensitive topic; defer for enhanced handling',
  },
  [WellnessCategory.MANAGER_TRAINING]: {
    primary: ContentPillar.HUMAN_PERFORMANCE,
    secondary: ContentPillar.AI_AUGMENTED_LEADERSHIP,
    rationale: 'People leadership capability',
  },
  [WellnessCategory.CULTURE_BELONGING]: {
    primary: ContentPillar.PERSONAL_OS,
    secondary: ContentPillar.HUMAN_PERFORMANCE,
    rationale: 'Individual identity + team',
  },
  [WellnessCategory.RESILIENCE_PROGRAMS]: {
    primary: ContentPillar.OPERATIONAL_RESILIENCE,
    secondary: null,
    rationale: 'Operational focus',
  },
  [WellnessCategory.WORK_FLEXIBILITY]: {
    primary: ContentPillar.FUTURE_OF_WORK,
    secondary: ContentPillar.PERSONAL_OS,
    rationale: 'Structural change',
  },
  [WellnessCategory.BURNOUT_PREVENTION]: {
    primary: ContentPillar.WELLNESS_SUSTAINABLE,
    secondary: ContentPillar.OPERATIONAL_RESILIENCE,
    rationale: 'Wellness + operational resilience',
  },
  [WellnessCategory.PHYSICAL_WELLNESS]: {
    primary: ContentPillar.WELLNESS_SUSTAINABLE,
    secondary: null,
    rationale: 'Core wellness pillar',
  },
  [WellnessCategory.PRODUCTIVITY_OPTIMIZATION]: {
    primary: ContentPillar.EXECUTION_EXCELLENCE,
    secondary: ContentPillar.WELLNESS_SUSTAINABLE,
    rationale: 'Bridges wellness and execution',
  },
};

const MIN_RANK_SCORE = 0.7;

/**
 * Quality/publishability score from available insight data.
 *
 * PHASE 1C TEMPORARY: rank_score isn't a real column on health_insights yet
 * (Phase 2 addition). Mirrors core/health/health_content_classifier.py's
 * _calculate_quality_score() — narrative_available + deterministic_findings.
 * Phase 2: replace with the real rank_score column from weekly_synthesis.
 */
function calculateQualityScore(insight: any): number {
  let score = 0.3;
  if (insight.narrative_available) {
    score = 0.8;
  } else if (insight.llm_narrative) {
    score = 0.6;
  }

  const findings = insight.deterministic_findings;
  if (findings) {
    if (Array.isArray(findings) || typeof findings === 'object') {
      const count = Array.isArray(findings) ? findings.length : Object.keys(findings).length;
      if (count > 0) score = Math.min(1.0, score + 0.2);
    } else if (typeof findings === 'string' && findings.trim()) {
      score = Math.min(1.0, score + 0.15);
    }
  }

  return score;
}

/**
 * GET /api/health-classifier/validate
 * Validate classifier on real health data
 */
async function handleValidate(req: NextRequest) {
  try {
    const sb = await createSupabaseServerClient();
    const since = new Date(Date.now() - 7 * 86_400_000).toISOString();

    // PHASE 1C: Query available columns (rank_score + sensitive calculated in Python backend)
    const { data: insights, error } = await sb
      .from('health_insights')
      .select('id, created_at, llm_narrative, narrative_available, deterministic_findings, committed_to_memory, source_articles')
      .gte('created_at', since)
      .order('created_at', { ascending: false })
      .limit(30);

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    if (!insights?.length) {
      return NextResponse.json({
        status: 'no_data',
        message: 'No health_insights in last 7 days',
      });
    }

    // Score insights
    const scored = insights
      .filter((i: any) => i.committed_to_memory !== false)
      .map((i: any) => ({ ...i, rank_score: calculateQualityScore(i) }))
      .filter((i: any) => i.rank_score >= MIN_RANK_SCORE)
      .map((i: any) => ({
        insight_id: i.id,
        rank_score: i.rank_score,
        publishable: true,
        pillar: ContentPillar.WELLNESS_SUSTAINABLE,
        has_articles: !!i.source_articles,
      }));

    const suppressed = insights.length - scored.length;
    const passRate = scored.length / insights.length;

    let recommendation = 'THRESHOLD APPROVED (pass rate 60-85%)';
    if (passRate < 0.6) {
      recommendation = 'LOWER THRESHOLD (too many rejections; try 0.65)';
    } else if (passRate > 0.85) {
      recommendation = 'RAISE THRESHOLD (too permissive; try 0.75)';
    }

    return NextResponse.json({
      status: 'success',
      samples_analyzed: insights.length,
      signals_published: scored.length,
      signals_suppressed: suppressed,
      pass_rate: passRate,
      current_threshold: MIN_RANK_SCORE,
      recommendation,
      scored_signals: scored.slice(0, 5),
    });
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message },
      { status: 500 }
    );
  }
}

/**
 * GET /api/health-classifier/audit-log
 * Get audit trail of suppressed signals
 */
async function handleAuditLog(req: NextRequest) {
  try {
    const sb = await createSupabaseServerClient();

    // Get recent insights that were discarded or marked sensitive
    const { data: suppressedInsights, error } = await sb
      .from('health_insights')
      .select('id, created_at, llm_narrative, committed_to_memory, reviewed_at')
      .or('committed_to_memory.is.false,reviewed_at.not.is.null')
      .order('reviewed_at', { ascending: false })
      .limit(20);

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    const auditLog = (suppressedInsights || []).map((i: any) => ({
      insight_id: i.id,
      reason: i.committed_to_memory === false ? 'Discarded by Captain' : 'Reviewed (possibly sensitive)',
      timestamp: i.reviewed_at || i.created_at,
      rank_score: i.rank_score,
    }));

    return NextResponse.json({
      total_suppressed: auditLog.length,
      audit_trail: auditLog,
    });
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message },
      { status: 500 }
    );
  }
}

/**
 * GET /api/health-classifier/mappings
 * Get wellness→pillar mappings
 */
async function handleMappings(req: NextRequest) {
  try {
    const mappings = Object.entries(PILLAR_MAPPINGS).map(([category, mapping]) => ({
      wellness_category: category,
      primary_pillar: mapping.primary,
      secondary_pillar: mapping.secondary,
      rationale: mapping.rationale,
      deferred_to_phase2: mapping.deferred_to_phase2 || false,
      phase2_reason: mapping.phase2_reason || null,
    }));

    return NextResponse.json({
      total_mappings: mappings.length,
      locked: mappings.filter((m: any) => !m.deferred_to_phase2).length,
      deferred: mappings.filter((m: any) => m.deferred_to_phase2).length,
      mappings,
    });
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message },
      { status: 500 }
    );
  }
}

/**
 * GET /api/health-classifier
 * Route dispatcher
 */
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const action = searchParams.get('action');

  switch (action) {
    case 'validate':
      return handleValidate(req);
    case 'audit-log':
      return handleAuditLog(req);
    case 'mappings':
      return handleMappings(req);
    default:
      return NextResponse.json({
        available_endpoints: [
          'GET ?action=validate — Validate classifier threshold',
          'GET ?action=audit-log — Get suppressed signals audit trail',
          'GET ?action=mappings — Get wellness→pillar mappings',
        ],
      });
  }
}
