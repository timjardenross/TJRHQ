// Connects HQ to the Intelligence delivery's own endpoints (incidents, products, source
// coverage). HQ reads what those endpoints return and never recomputes clustering, tiers,
// products or source health. Each source reports one of three honest states:
//   ok          the endpoint answered with data
//   off         the Intelligence programme's flag is off in this environment
//   unavailable the endpoint answered but the data is not there yet (migration not applied) or it failed
import { getJson } from './data';
import { normaliseRisk } from './vocab';
import type { HqIntelItem } from './model';
import { incidentHref, productHref } from '@/lib/intelligenceLinks';
import type { IncidentRow } from '@/lib/incidents';
import type { ClassifiedSource, SourceState } from '@/lib/sourceEffectiveness';
import type { IntelligenceProduct, ProductException2 } from '@/lib/intelligenceProducts';

export type ExtraState = 'ok' | 'off' | 'unavailable';

export function mapIncident(r: IncidentRow): HqIntelItem {
  return {
    id: `incident:${r.incident_key}`,
    kind: r.tier === 'IMMEDIATE_ALERT' ? 'Incident (alert level)' : 'Incident (material)',
    lens: 'Technical',
    title: r.headline,
    summary: `${r.n_reports} ${r.n_reports === 1 ? 'report' : 'reports'}. Restoration: ${r.restoration_status.replace(/_/g, ' ')}.`,
    why: r.why || null,
    youNeedTo: null,
    risk: r.tier === 'IMMEDIATE_ALERT' ? 'High' : 'Medium',
    // The clustering does not carry an evidence-quality grade, so none is claimed.
    evidence: 'Unknown',
    corroboration: r.n_reports,
    needsYou: true,
    watching: false,
    when: r.last_report_at,
    url: null,
    sourceName: null,
    legacyHref: incidentHref(r.incident_key),
  };
}

export function mapProductException(e: ProductException2): HqIntelItem {
  const risk = normaliseRisk(e.severity);
  return {
    id: `product:${e.dedupe_key}`,
    kind: 'Product exception',
    lens: 'Technical',
    title: e.title,
    summary: e.detail,
    why: `From ${e.product_title}.`,
    youNeedTo: null,
    risk,
    evidence: 'Unknown',
    corroboration: e.evidence_ids?.length ?? null,
    needsYou: risk === 'High',
    watching: risk !== 'High',
    when: e.generated_for,
    url: null,
    sourceName: e.product_title,
    legacyHref: e.href || productHref(e.product_key),
  };
}

export interface IntelExtras {
  incidents: { state: ExtraState; items: HqIntelItem[] };
  products: { state: ExtraState; products: IntelligenceProduct[]; items: HqIntelItem[] };
  coverage: { state: ExtraState; counts: Record<SourceState, number> | null; limitationsLine: string; notHealthy: ClassifiedSource[] };
}

export async function loadIntelExtras(): Promise<IntelExtras> {
  const [inc, prod, cov] = await Promise.all([
    getJson<{ enabled?: boolean; available?: boolean; incidents?: IncidentRow[] }>('/api/intelligence-workbench/incidents?scope=attention'),
    getJson<{ available?: boolean; products?: IntelligenceProduct[]; exceptions?: ProductException2[] }>('/api/intelligence-workbench/products'),
    getJson<{ summary?: Record<SourceState, number>; sources?: ClassifiedSource[]; limitations_line?: string }>('/api/intelligence-workbench/source-coverage'),
  ]);
  const incidents: IntelExtras['incidents'] = !inc.ok ? { state: 'unavailable', items: [] }
    : inc.data.enabled === false ? { state: 'off', items: [] }
    : inc.data.available === false ? { state: 'unavailable', items: [] }
    : { state: 'ok', items: (inc.data.incidents ?? []).map(mapIncident) };
  const products: IntelExtras['products'] = !prod.ok || prod.data.available === false
    ? { state: 'unavailable', products: [], items: [] }
    : { state: 'ok', products: prod.data.products ?? [], items: (prod.data.exceptions ?? []).map(mapProductException) };
  const coverage: IntelExtras['coverage'] = !cov.ok || !cov.data.summary
    ? { state: 'unavailable', counts: null, limitationsLine: '', notHealthy: [] }
    : { state: 'ok', counts: cov.data.summary, limitationsLine: cov.data.limitations_line ?? '', notHealthy: (cov.data.sources ?? []).filter((s) => s.state !== 'HEALTHY' && s.state !== 'QUIET') };
  return { incidents, products, coverage };
}
