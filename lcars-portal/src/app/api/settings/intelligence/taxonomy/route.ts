// TJR HQ Settings → Intelligence. Read-only mirror of
// config/osint_intelligence_missions.json — the ONE taxonomy of technical
// priority categories and health domain tags, already the shared source
// of truth for intelligence/classification/relevance_gate.py (technical)
// and tools/health-osint/priority_domains.py (health). Per
// OSINT_MISSION_CONFIG_DESIGN.md this file is git-tracked and hand-edited
// deliberately (auditability) — this route never writes to it, only reads
// labels/keys for Settings' checkboxes. What the Captain enables/disables
// is a separate overlay stored in user_settings (lib/settings.ts), read by
// the Python side via intelligence/settings_store.py.
//
// Same fs-read-with-fallback shape as
// api/health-osint/intelligence-summary/route.ts, so a bad deploy (missing
// REPO_ROOT, file not present in this runtime) degrades to a smaller
// static list rather than a broken Settings page.

import { NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import fs from 'fs';
import path from 'path';

interface TechnicalCategory {
  key: string;
  label: string;
}

interface HealthTierTags {
  key: string;
  label: string;
  tags: { key: string; label: string }[];
}

const FALLBACK_TECHNICAL_CATEGORIES: TechnicalCategory[] = [
  { key: 'operational_resilience', label: 'Operational Resilience' },
  { key: 'cyber_security', label: 'Cybersecurity' },
  { key: 'technology_infrastructure', label: 'Technology Infrastructure' },
  { key: 'third_party_dependency', label: 'Major Third-Party Dependencies' },
  { key: 'telecommunications', label: 'Telecommunications' },
  { key: 'banking_financial', label: 'Banking / Financial Services Resilience' },
  { key: 'regulatory_resilience', label: 'Regulatory Resilience Obligations' },
  { key: 'critical_infrastructure', label: 'Critical Infrastructure' },
];

const FALLBACK_HEALTH_TIERS: HealthTierTags[] = [
  {
    key: 'core_high_priority',
    label: 'Core',
    tags: [
      { key: 'neuro_autism', label: 'Autism' },
      { key: 'neuro_adhd', label: 'ADHD' },
      { key: 'neuro_audhd', label: 'AuDHD' },
      { key: 'neuro_burnout', label: 'Autistic / neurodivergent burnout' },
      { key: 'neuro_regulation', label: 'Nervous-system regulation' },
      { key: 'neuro_sensory', label: 'Sensory processing' },
      { key: 'neuro_executive_function', label: 'Executive functioning' },
    ],
  },
  {
    key: 'recovery_function',
    label: 'Recovery & Function',
    tags: [
      { key: 'chronic_pain', label: 'Chronic pain' },
      { key: 'neuro_sleep', label: 'Sleep' },
      { key: 'performance', label: 'Exercise / physical functioning' },
      { key: 'mental_health', label: 'Stress & recovery' },
      { key: 'neuro_treatment', label: 'Cognitive performance' },
    ],
  },
  {
    key: 'contextual',
    label: 'Work & Functioning',
    tags: [
      { key: 'neuro_work', label: 'Workplace neurodiversity' },
      { key: 'neuro_australia_policy', label: 'Australian policy context' },
      { key: 'neuro_lived_experience', label: 'Lived experience' },
      { key: 'supplement', label: 'Supplements' },
    ],
  },
];

function humanizeLabel(key: string): string {
  return key
    .replace(/^neuro_/, '')
    .replace(/^chronic_pain_/, 'chronic pain: ')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function loadTaxonomy(): { technical: TechnicalCategory[]; health: HealthTierTags[] } {
  try {
    const REPO_ROOT = process.env.REPO_ROOT ? path.resolve(process.env.REPO_ROOT) : path.resolve(process.cwd(), '..');
    const raw = fs.readFileSync(path.join(REPO_ROOT, 'config', 'osint_intelligence_missions.json'), 'utf8');
    const config = JSON.parse(raw);

    const technical: TechnicalCategory[] = (config?.technical?.priority_categories ?? []).map(
      (c: { key: string; label: string }) => ({ key: c.key, label: c.label }),
    );

    const tiers = config?.health?.domain_tiers ?? {};
    const health: HealthTierTags[] = Object.entries(tiers as Record<string, { label: string; tags: string[] }>).map(
      ([key, tier]) => ({
        key,
        label: tier.label,
        tags: tier.tags.map((t) => ({ key: t, label: humanizeLabel(t) })),
      }),
    );

    if (technical.length === 0 || health.length === 0) throw new Error('empty taxonomy in config');
    return { technical, health };
  } catch {
    return { technical: FALLBACK_TECHNICAL_CATEGORIES, health: FALLBACK_HEALTH_TIERS };
  }
}

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Not authenticated.' }, { status: 401 });
  }
  return NextResponse.json(loadTaxonomy());
}
