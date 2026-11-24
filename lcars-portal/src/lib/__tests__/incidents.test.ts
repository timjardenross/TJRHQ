import { describe, it, expect } from 'vitest';
import {
  dedupeIncidents,
  fetchIncidentSnapshot,
  incidentViewEnabled,
  lifecycleSummary,
  needsAttention,
  toDecisionItem,
  type IncidentRow,
} from '@/lib/incidents';
import { buildNeedsYouItems, type NeedsYouBuildInputs } from '@/lib/commandState';
import { incidentHref } from '@/lib/intelligenceLinks';

function row(over: Partial<IncidentRow> = {}): IncidentRow {
  return {
    incident_key: 'inc-1ac9ea52',
    headline: 'Microsoft 365 global outage',
    tier: 'IMMEDIATE_ALERT',
    restoration_status: 'ongoing',
    n_reports: 4,
    why: 'high materiality, stated impact, live disruption',
    reports: [
      { relation: 'NEW', event_id: 'a', title: 'first', published_at: '2026-11-12T20:16:00Z' },
      { relation: 'SUBSEQUENT', event_id: 'b', title: 'second', published_at: '2026-11-12T21:00:00Z' },
      { relation: 'RESTORATION_UPDATE', event_id: 'c', title: 'back', published_at: '2026-11-13T03:33:00Z', restoration: 'full' },
      { relation: 'RELATED', event_id: 'd', title: 'cost', published_at: null },
    ],
    material_exception: false,
    snapshot_at: '2026-11-13T04:00:00Z',
    last_report_at: '2026-11-13T03:33:00Z',
    ...over,
  };
}

function fakeSb(result: { data: unknown[] | null; error: { message: string } | null } | 'throw') {
  const chain: Record<string, unknown> = {};
  for (const m of ['select', 'gte', 'order', 'limit']) chain[m] = () => chain;
  chain.then = (resolve: (v: unknown) => void, reject: (e: unknown) => void) =>
    result === 'throw' ? Promise.reject(new Error('boom')).then(resolve, reject) : Promise.resolve(result).then(resolve);
  return { from: () => chain };
}

describe('incidentViewEnabled', () => {
  it('is OFF by default and only on an explicit truthy value', () => {
    expect(incidentViewEnabled({})).toBe(false);
    expect(incidentViewEnabled({ INCIDENT_VIEW_V1: '0' })).toBe(false);
    expect(incidentViewEnabled({ INCIDENT_VIEW_V1: ' TRUE ' })).toBe(true);
  });
});

describe('needsAttention / dedupeIncidents', () => {
  it('alert-level incidents and material exceptions need attention; monitoring and context do not', () => {
    expect(needsAttention(row())).toBe(true);
    expect(needsAttention(row({ tier: 'SCHEDULED_BRIEF', material_exception: true }))).toBe(true);
    expect(needsAttention(row({ tier: 'SCHEDULED_BRIEF', material_exception: false }))).toBe(false);
    expect(needsAttention(row({ tier: 'MONITOR', material_exception: true }))).toBe(false);
  });

  it('keeps one entry per incident_key, newest snapshot wins, alert tier first', () => {
    const rows = [
      row({ snapshot_at: '2026-11-13T01:00:00Z', tier: 'SCHEDULED_BRIEF' }),
      row({ snapshot_at: '2026-11-13T05:00:00Z', tier: 'IMMEDIATE_ALERT' }),
      row({ incident_key: 'inc-zzzz0000', tier: 'MONITOR' }),
    ];
    const out = dedupeIncidents(rows);
    expect(out.map((r) => r.incident_key)).toEqual(['inc-1ac9ea52', 'inc-zzzz0000']);
    expect(out[0].tier).toBe('IMMEDIATE_ALERT');
  });
});

describe('lifecycle and decision item', () => {
  it('summarises the lifecycle by report relation', () => {
    expect(lifecycleSummary(row())).toBe('1 new · 1 subsequent · 1 restoration · 1 related');
  });

  it('the Decisions id and the Needs You id are built from the same incident_key as the Telegram alert', () => {
    const d = toDecisionItem(row());
    expect(d.id).toBe('inc:inc-1ac9ea52');
    expect(d.href).toBe('/intelligence-workbench?tab=incidents#inc-1ac9ea52');
    const inputs = { incidentAttention: [{ incidentKey: d.incidentKey, title: d.title, detail: d.detail }, { incidentKey: d.incidentKey, title: d.title, detail: d.detail }] };
    const items = buildNeedsYouItems(baseInputs(inputs));
    const inc = items.filter((i) => i.id.startsWith('incident-'));
    expect(inc).toHaveLength(1); // duplicate key collapses: one incident, one entry
    expect(inc[0].id).toBe('incident-inc-1ac9ea52');
  });
});

describe('fetchIncidentSnapshot', () => {
  it('returns deduped rows, attention-only when asked', async () => {
    const sb = fakeSb({ data: [row(), row({ incident_key: 'inc-m', tier: 'MONITOR' })], error: null });
    const all = await fetchIncidentSnapshot(sb);
    expect(all).toEqual({ available: true, incidents: expect.any(Array) });
    expect(all.incidents).toHaveLength(2);
    expect((await fetchIncidentSnapshot(sb, { attentionOnly: true })).incidents).toHaveLength(1);
  });

  it('a missing table or a thrown error is unavailable, never an empty all-clear and never a throw', async () => {
    expect(await fetchIncidentSnapshot(fakeSb({ data: null, error: { message: 'relation does not exist' } }))).toEqual({ available: false, incidents: [] });
    expect(await fetchIncidentSnapshot(fakeSb('throw'))).toEqual({ available: false, incidents: [] });
  });
});

function baseInputs(extra: Partial<NeedsYouBuildInputs>): NeedsYouBuildInputs {
  return {
    emergency: null, briefingError: false, interruptNow: 0, contentAwaitingPublish: 0, oldestContentAwaitingPublish: null, wellnessRiskFlags: 0,
    notebookReadyCount: 0, capturePending: 0, oldestCapturePending: null, evolutionPendingCount: 0, evolutionHighestValueTitle: null,
    engineeringApprovalsCount: 0, oldestEngineeringApproval: null, hqPosture: null, hqAttentionItems: [], criticalAlerts: [], ...extra,
  };
}

describe('buildNeedsYouItems default output', () => {
  it('adds no incident item when incidentAttention is absent (flag OFF)', () => {
    expect(buildNeedsYouItems(baseInputs({})).some((i) => i.id.startsWith('incident-'))).toBe(false);
  });
});

describe('one incident = one entry across Home, Hub and Decisions', () => {
  it('duplicate snapshots collapse once and every surface links the same canonical tab URL', () => {
    const rows = [row({ snapshot_at: '2026-11-13T01:00:00Z' }), row({ snapshot_at: '2026-11-13T05:00:00Z' }), row({ snapshot_at: '2026-11-13T09:00:00Z' })];
    const deduped = dedupeIncidents(rows);
    expect(deduped).toHaveLength(1); // feeds Home (needs-attention route) and Decisions
    const decision = toDecisionItem(deduped[0]);
    const hub = buildNeedsYouItems(baseInputs({ incidentAttention: deduped.map((r) => ({ incidentKey: r.incident_key, title: r.headline, detail: 'd' })) }))
      .filter((i) => i.id.startsWith('incident-'));
    expect(hub).toHaveLength(1);
    const canonical = incidentHref(deduped[0].incident_key);
    expect(canonical).toBe('/intelligence-workbench?tab=incidents#inc-1ac9ea52');
    expect(decision.href).toBe(canonical);
    expect(hub[0].href).toBe(canonical);
  });
});
