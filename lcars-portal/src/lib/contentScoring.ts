// Content scoring — Content Workbench (COMMS-002)
//
// A capture-time TypeScript port of the pillar classification + content
// relevance + ranking logic in intelligence/classification/content_classifier.py
// and intelligence/ranking/content_ranker.py. Ported (not called via subprocess)
// because the deployed Next.js app has no Python runtime on Vercel — the exact
// same precedent as signalsToOpportunities.ts porting
// core/content/signal_opportunity_converter.py. Both must stay behaviourally
// identical for the pillar/keyword/weight logic; the Python originals remain
// the CLI/cron entry point for scoring signals from intelligence_events.
//
// This module is used ONLY by /api/content-workbench/capture — it does not
// touch, import, or affect lib/capture.ts or /api/content/draft (the existing
// Capture Workbench's 'comms' capture type is unchanged and still bypasses
// scoring, exactly as it does today).
//
// Deliberate difference from the Python original: score_for_content() rejects
// events with pillar_score === 0 (filters noisy automated ingestion). A manual
// capture is user intent, not a noisy source — it is never rejected here, only
// scored and defaulted to the DEFAULT_PILLAR when no keyword matches.

export interface Pillar {
  key: string;
  name: string;
  strategicDomain: string;
  keywords: readonly string[];
}

// Ported verbatim from platform-runtime/lib/comms/pillars.py (COMMS-001 WP2).
export const PILLARS: readonly Pillar[] = [
  {
    key: 'operational_resilience',
    name: 'Operational Resilience',
    strategicDomain: 'Career & Professional Impact',
    keywords: [
      'resilience', 'risk', 'outage', 'incident', 'recovery', 'continuity',
      'disruption', 'ori', 'threat', 'exposure',
      'cyber', 'vulnerability', 'breach', 'ransomware', 'failover', 'redundancy',
      'apra', 'cirmp', 'critical infrastructure', 'crisis', 'cascade',
      'single point of failure', 'vendor risk', 'supply chain', 'high availability',
      'disaster', 'backup', 'stress test', 'systemic risk', 'operational risk',
      'third party risk', 'service disruption', 'system failure', 'restoration',
      'tabletop', 'playbook', 'runbook', 'drill', 'exercise', 'simulation',
    ],
  },
  {
    key: 'business_continuity',
    name: 'Business Continuity',
    strategicDomain: 'Career & Professional Impact',
    keywords: [
      'continuity', 'bcp', 'cps230', 'cps 230', 'regulator', 'compliance',
      'recovery time', 'rto', 'rpo', 'dependency',
      'business impact', 'bia', 'disaster recovery', 'continuity planning',
      'crisis management', 'emergency response', 'business disruption',
      'service resumption', 'workaround', 'alternate site', 'succession',
      'plan testing', 'rehearsal', 'prudential', 'regulatory',
      'maximum tolerable downtime', 'mtd', 'critical function',
      'recovery point objective', 'recovery time objective', 'backup site',
    ],
  },
  {
    key: 'human_performance',
    name: 'Human Performance',
    strategicDomain: 'Health & Human Systems',
    keywords: [
      'performance', 'capacity', 'energy', 'focus', 'burnout', 'load',
      'nervous system', 'regulation', 'recovery', 'sustainable',
      'high performance', 'mental performance', 'cognitive load', 'decision fatigue',
      'peak performance', 'flow state', 'pressure', 'stress management',
      'concentration', 'deep work', 'deliberate practice', 'grit',
      'mental toughness', 'performance psychology', 'performance coaching',
      'mental fitness', 'cognitive function', 'executive function',
      'under pressure', 'high achiever', 'elite performance', 'athlete mindset',
      'cognitive performance', 'brain performance', 'sustained performance',
    ],
  },
  {
    key: 'wellness_sustainable_performance',
    name: 'Wellness & Sustainable Performance',
    strategicDomain: 'Coaching Enterprise',
    keywords: [
      'wellness', 'wellbeing', 'sleep', 'movement', 'nutrition', 'stress',
      'coaching', 'habit', 'rest', 'balance',
      'mental health', 'mindfulness', 'meditation', 'self-care', 'well-being',
      'work-life', 'work life', 'boundaries', 'flourishing', 'vitality',
      'energy management', 'burnout prevention', 'longevity', 'healthy habits',
      'occupational health', 'employee wellbeing', 'workplace wellness',
      'emotional wellbeing', 'positive psychology', 'gratitude', 'purpose',
      'meaning', 'fulfillment', 'psychological safety', 'self-compassion',
      'compassion fatigue', 'overwork', 'exhaustion', 'mindset',
      'lifestyle', 'sustainable high performance',
      'emotional intelligence', 'eq', 'inner game', 'recovery science',
      'restorative', 'regeneration', 'recharge', 'thriving', 'flourish',
      'wellbeing at work', 'happiness at work',
      'engagement', 'workplace mental health', 'psychological wellbeing',
    ],
  },
  {
    key: 'ai_augmented_leadership',
    name: 'AI-Augmented Leadership',
    strategicDomain: 'Career & Professional Impact',
    keywords: [
      'ai', 'agent', 'llm', 'automation', 'augmented', 'copilot', 'model',
      'intelligence', 'assistant', 'human-in-the-loop',
      'artificial intelligence', 'machine learning', 'generative ai', 'genai',
      'gpt', 'chatgpt', 'large language model', 'neural network', 'deep learning',
      'ai adoption', 'ai strategy', 'ai ethics', 'ai governance',
      'digital transformation', 'technology leadership', 'data-driven',
      'ai-powered', 'responsible ai', 'ai tool', 'agentic',
      'foundation model', 'prompt', 'rag', 'retrieval-augmented',
    ],
  },
  {
    key: 'personal_operating_systems',
    name: 'Personal Operating Systems',
    strategicDomain: 'Starship Endeavour',
    keywords: [
      'operating system', 'personal os', 'endeavour', 'starship', 'system',
      'command', 'officer', 'governance', 'capability', 'workflow',
      'personal productivity', 'life design', 'planning system', 'time management',
      'personal management', 'task management', 'personal effectiveness',
      'routines', 'rituals', 'goal setting', 'quarterly review', 'weekly review',
      'knowledge management', 'productivity system', 'life optimization',
      'personal strategy', 'personal leadership', 'self-leadership',
      'self-management', 'second brain', 'pkm', 'personal knowledge',
      'intentional', 'deliberate', 'systems thinking', 'life architecture',
    ],
  },
  {
    key: 'future_of_work',
    name: 'Future of Work',
    strategicDomain: 'Career & Professional Impact',
    keywords: [
      'future of work', 'remote', 'productivity', 'team', 'operating model',
      'org', 'talent', 'automation', 'role',
      'hybrid work', 'distributed team', 'flexible work', 'workforce',
      'employee experience', 'culture', 'collaboration', 'async',
      'asynchronous', 'digital workplace', 'workforce strategy',
      'talent management', 'retention', 'onboarding', 'leadership development',
      'organizational change', 'org design', 'agile', 'ways of working',
      'future skills', 'upskilling', 'reskilling', 'workforce planning',
      'new ways of working', 'work design', 'job design', 'work model',
    ],
  },
  {
    key: 'decision_quality_governance',
    name: 'Decision Quality & Governance',
    strategicDomain: 'Starship Endeavour',
    keywords: [
      'decision', 'governance', 'judgement', 'judgment', 'trade-off',
      'prioritisation', 'prioritization', 'approval', 'authority', 'review',
      'decision making', 'decision-making', 'strategic decision', 'board',
      'risk appetite', 'accountability', 'mandate', 'delegated authority',
      'escalation', 'committee', 'steering', 'oversight', 'due diligence',
      'framework', 'policy', 'control', 'assurance', 'audit', 'risk governance',
      'corporate governance', 'board governance', 'decision framework',
      'mental models', 'cognitive bias', 'heuristics', 'rationality',
      'evidence-based', 'critical thinking', 'analytical', 'sense-making',
    ],
  },
] as const;

export const PILLARS_BY_KEY: Record<string, Pillar> = Object.fromEntries(PILLARS.map((p) => [p.key, p]));
export const DEFAULT_PILLAR: Pillar = PILLARS_BY_KEY['personal_operating_systems'];

const CAPTAIN_FOCUS_BASE = [
  'operational resilience', 'resilience', 'cps 230', 'ai', 'leadership',
  'decision', 'coaching', 'performance', 'continuity', 'governance',
  'endeavour', 'ai-augmented', 'personal operating', 'future of work',
  'thought leadership', 'human performance', 'wellness',
];

// Ported from content_classifier.py's _ANGLE_TEMPLATES — used to pre-fill
// research_angle for the human to confirm or override, not to auto-write copy.
const ANGLE_TEMPLATES: Record<string, Array<[string[], string]>> = {
  operational_resilience: [
    [['outage', 'disruption', 'incident'], 'Lessons from this disruption for building resilient operations'],
    [['regulation', 'compliance', 'apra'], 'What this regulatory signal means for resilience practitioners'],
    [[], 'Operational resilience: what this signal means for leaders'],
  ],
  business_continuity: [
    [['cps 230', 'cps230', 'apra'], 'CPS 230 lens: how this regulatory development shapes continuity practice'],
    [['third party', 'vendor', 'outsourced'], 'Third-party resilience: what this signal means for BCPs'],
    [[], 'Business continuity insight: what practitioners should notice here'],
  ],
  human_performance: [
    [['burnout', 'stress', 'fatigue', 'load'], 'Human capacity under pressure: the leadership angle'],
    [['performance', 'focus', 'productivity'], "Performance sustainability: a practitioner's take"],
    [[], 'Human performance lens: why this matters for high-performing leaders'],
  ],
  wellness_sustainable_performance: [
    [['sleep', 'recovery', 'rest'], 'The recovery science behind sustained performance'],
    [['coaching', 'wellness', 'wellbeing'], 'Coaching perspective: applying this in practice'],
    [[], 'Sustainable performance: translating this signal into practice'],
  ],
  ai_augmented_leadership: [
    [['ai', 'llm', 'agent', 'automation'], 'AI leadership: what this development means for executives adopting AI'],
    [['risk', 'governance'], 'AI governance: the accountability angle senior leaders must own'],
    [[], 'AI-augmented leadership: what this signal means for the next wave of leaders'],
  ],
  personal_operating_systems: [
    [['system', 'command', 'workflow', 'governance'], 'Personal operating systems: the systems-thinking angle'],
    [[], 'Running your work like a well-governed system: a practical angle'],
  ],
  future_of_work: [
    [['remote', 'team', 'org', 'talent'], 'Future of work: the operating model implication'],
    [['automation', 'ai', 'productivity'], 'The automation era: what this means for how we work'],
    [[], 'Future of work: what this signal means for the evolving professional landscape'],
  ],
  decision_quality_governance: [
    [['decision', 'judgement', 'judgment', 'approval'], 'Decision quality: the systemic angle leaders miss'],
    [['governance', 'board', 'review'], 'Governance insight: how this shapes better decision architecture'],
    [[], 'Decision quality: translating this signal into better leadership practice'],
  ],
};

/** Pure: best-matching pillar for a piece of text + the match score (count of distinct keyword hits). */
export function classifyPillar(text: string): { pillar: Pillar; score: number } {
  const hay = (text || '').toLowerCase();
  let best = DEFAULT_PILLAR;
  let bestScore = 0;
  for (const p of PILLARS) {
    const score = p.keywords.reduce((acc, kw) => (hay.includes(kw) ? acc + 1 : acc), 0);
    if (score > bestScore) {
      best = p;
      bestScore = score;
    }
  }
  return { pillar: best, score: bestScore };
}

function deriveAngle(pillarKey: string, pillarName: string, text: string, captainFocus: boolean): string {
  const hay = text.toLowerCase();
  const templates = ANGLE_TEMPLATES[pillarKey] ?? [];
  for (const [keywords, angle] of templates) {
    if (keywords.length === 0 || keywords.some((kw) => hay.includes(kw))) {
      return angle + (captainFocus ? ' (captain-focus signal)' : '');
    }
  }
  return `Angle: ${pillarName} — how this connects to what practitioners need to hear`;
}

export interface CaptureScore {
  pillarKey: string;
  pillarName: string;
  contentRelevance: number; // 0-1
  captainFocus: boolean;
  suggestedAngle: string;
  rankScore: number; // 0-100, same scale as content_signals.rank_score
}

/**
 * Score a manually-captured text for the Content Workbench.
 *
 * A capture-time analogue of content_classifier.score_for_content() +
 * content_ranker.rank(), with no source event to draw source_confidence_weight,
 * operational_relevance, or cross-source rank_score from — those default to
 * the same neutral values a brand-new, unconfirmed source would get
 * (source_confidence_weight=0.5, operational_relevance=0, cross_source=0),
 * and recency is always 1.0 (captured now). Unlike the Python original, this
 * never returns null — a manual capture is never rejected for a zero pillar
 * match, only defaulted to DEFAULT_PILLAR, consistent with Capture Workbench's
 * review-first / nothing-auto-routes-without-your-say ethos.
 */
export function scoreCapture(text: string): CaptureScore {
  const { pillar, score: pillarScore } = classifyPillar(text);

  // content_relevance = min(1, pillar_score*0.20 + source_confidence_weight*0.30
  //                     + operational_relevance*0.15 + cross_source_rank_boost)
  // with source_confidence_weight defaulted to 0.5, operational_relevance to 0,
  // and no cross-source rank_score available for a fresh manual capture.
  const contentRelevance = Math.min(1, pillarScore * 0.2 + 0.5 * 0.3);

  const hay = text.toLowerCase();
  const captainFocus = CAPTAIN_FOCUS_BASE.some((kw) => hay.includes(kw));

  const suggestedAngle = deriveAngle(pillar.key, pillar.name, text, captainFocus);

  // rank() — pillar_fit and source_quality both collapse to content_relevance,
  // as in the Python original.
  const pillarFit = Math.min(1, contentRelevance);
  const strategic = (captainFocus ? 0.6 : 0.2) + Math.min(0.4, contentRelevance * 0.4);
  const recency = 1.0; // captured now, always within useful life
  const cross = 0; // no cross-source confirmation for a manual capture
  const quality = Math.min(1, contentRelevance);

  const raw = pillarFit * 0.3 + strategic * 0.25 + recency * 0.2 + cross * 0.15 + quality * 0.1;
  const rankScore = Math.round(raw * 100 * 10000) / 10000;

  return {
    pillarKey: pillar.key,
    pillarName: pillar.name,
    contentRelevance: Math.round(contentRelevance * 1000) / 1000,
    captainFocus,
    suggestedAngle,
    rankScore,
  };
}
