// @vitest-environment jsdom
//
// Acceptance audit (post-#40/#46): "Given identical inputs, prove both
// surfaces agree on command posture, Human Systems state, genuine Needs
// You items, intelligence materiality, Emergency materiality, and HQ
// intervention state." Captain's Chair and LifeOS share the exact same
// commandState.ts/captainsChairSynthesis.ts functions, so agreement is
// structurally guaranteed by construction — but "structurally guaranteed"
// is a claim, not a test. This file renders BOTH pages against identical
// mocked fetch responses and asserts they report the same command truth,
// so a future edit to one page's wiring that breaks parity fails loudly
// here rather than only being caught by a human reading two page-level
// test files that happen to use similar-but-not-identical fixtures.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

vi.mock('@/lib/useAlerts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/useAlerts')>();
  return {
    ...actual,
    useAlerts: () => ({ alerts: [], isLoading: false, failedSources: 0, totalSources: 6 }),
    useAlertCount: () => 0,
  };
});
vi.mock('@/lib/capture', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/capture')>();
  return {
    ...actual,
    fetchCaptureAnalytics: async () => ({ today: 0, this_week: 0, pending: 0, by_source: {}, by_classification: {} }),
    fetchInboxCaptures: async () => [],
  };
});
vi.mock('@/lib/supabase-browser', () => ({
  createSupabaseBrowserClient: () => ({
    from: () => ({
      select: () => ({
        eq: () => Promise.resolve({ data: [], error: null }),
        in: () => ({ order: () => ({ limit: () => Promise.resolve({ data: [], error: null }) }) }),
      }),
      insert: () => Promise.resolve({ error: null }),
    }),
  }),
}));
vi.mock('@/components/TodaysBriefPanel', () => ({ TodaysBriefPanel: () => null }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: () => {}, replace: () => {} }),
  usePathname: () => '/',
}));

import CaptainsChairWorkbench from '../captains-chair-workbench/page';
import LifeOSHub from '../hub/page';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const DEFAULT_HUMAN_SYSTEMS_CONTEXT = {
  posture: 'STEADY',
  posture_message: 'Maintain current pace. Avoid unnecessary load increases.',
  available_capacity: 'green',
  capacity_direction: 'sustainable',
  stimulation_context: null,
  executive_function_context: null,
  regulation_context: null,
  strain_or_recovery_context: { trajectory: 'stable', strategic_posture: 'steady', message: '' },
  active_loads: [],
  relevant_needs: [],
  freshness: { status: 'fresh', last_checkin_at: new Date().toISOString() },
  confidence: 'moderate',
  has_checkin_today: true,
};

const DEFAULT_HQ_STATUS = {
  posture: 'normal',
  headline: 'HQ is operating normally',
  captainSummary: {
    hq_posture: 'NORMAL',
    summary: 'HQ is operating normally',
    material_degradations: [],
    needs_attention_count: 0,
    unknown_material_count: 0,
    last_updated: new Date().toISOString(),
    freshness: 'live',
  },
  needsAttentionCount: 0,
  attentionItems: [] as Array<{ title: string; detail: string }>,
};

function attentionHqStatus(title: string, detail: string) {
  return {
    ...DEFAULT_HQ_STATUS,
    posture: 'attention',
    headline: 'HQ needs your attention',
    captainSummary: { ...DEFAULT_HQ_STATUS.captainSummary, hq_posture: 'ATTENTION', summary: `HQ needs your attention — ${detail}`, needs_attention_count: 1 },
    needsAttentionCount: 1,
    attentionItems: [{ title, detail }],
  };
}

function mockFetchByUrl(routes: Record<string, unknown>) {
  const merged = {
    '/api/human-systems/context': DEFAULT_HUMAN_SYSTEMS_CONTEXT,
    '/api/agent-status-workbench/overview': DEFAULT_HQ_STATUS,
    '/api/emergency-alerts': { alerts: [] },
    ...routes,
  };
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    for (const [prefix, body] of Object.entries(merged)) {
      if (url.startsWith(prefix)) {
        return Promise.resolve({ ok: true, json: async () => body } as Response);
      }
    }
    return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
  }));
}

describe('Command Experience parity — Captain\'s Chair and LifeOS agree on the same truth', () => {
  it('agree on a quiet STEADY day with nothing needs you', async () => {
    mockFetchByUrl({});
    const chair = render(<CaptainsChairWorkbench />);
    expect((await chair.findAllByText('STEADY')).length).toBeGreaterThanOrEqual(1);
    await waitFor(() => expect(chair.getByText('✓ Nothing needs you right now.')).toBeInTheDocument());
    chair.unmount();

    mockFetchByUrl({});
    const hub = render(<LifeOSHub />);
    expect(await hub.findByText('STEADY TODAY')).toBeInTheDocument();
    await waitFor(() => expect(hub.getByText('✓ Nothing needs your attention.')).toBeInTheDocument());
    hub.unmount();
  });

  it('agree that an emergency_warning forces RESPOND and a matching Needs You item on both surfaces', async () => {
    const routes = {
      '/api/emergency-alerts': { alerts: [{ severity: 'emergency_warning', headline: 'Emergency warning — Bushfire, Blue Mountains' }] },
    };

    mockFetchByUrl(routes);
    const chair = render(<CaptainsChairWorkbench />);
    expect(await chair.findByText('RESPOND')).toBeInTheDocument();
    expect((await chair.findAllByText('Emergency warning — Bushfire, Blue Mountains')).length).toBeGreaterThanOrEqual(1);
    chair.unmount();

    mockFetchByUrl(routes);
    const hub = render(<LifeOSHub />);
    expect(await hub.findByText('RESPOND TODAY')).toBeInTheDocument();
    expect((await hub.findAllByText('Emergency warning — Bushfire, Blue Mountains')).length).toBeGreaterThanOrEqual(1);
    hub.unmount();
  });

  it('agree that HQ ATTENTION forces RESPOND with a matching intervention item on both surfaces', async () => {
    const routes = {
      '/api/agent-status-workbench/overview': attentionHqStatus('Google Calendar authentication expired', 'Reconnect required.'),
    };

    mockFetchByUrl(routes);
    const chair = render(<CaptainsChairWorkbench />);
    expect(await chair.findByText('RESPOND')).toBeInTheDocument();
    expect(await chair.findByText('Google Calendar authentication expired')).toBeInTheDocument();
    chair.unmount();

    mockFetchByUrl(routes);
    const hub = render(<LifeOSHub />);
    expect(await hub.findByText('RESPOND TODAY')).toBeInTheDocument();
    expect(await hub.findByText('Google Calendar authentication expired')).toBeInTheDocument();
    hub.unmount();
  });

  it('agree that HQ DEGRADED never forces RESPOND or a Needs You item on either surface', async () => {
    const degraded = {
      ...DEFAULT_HQ_STATUS,
      posture: 'degraded',
      captainSummary: { ...DEFAULT_HQ_STATUS.captainSummary, hq_posture: 'DEGRADED', summary: 'HQ is degraded — Morning Brief source coverage is incomplete.' },
    };
    const routes = { '/api/agent-status-workbench/overview': degraded };

    mockFetchByUrl(routes);
    const chair = render(<CaptainsChairWorkbench />);
    expect((await chair.findAllByText('STEADY')).length).toBeGreaterThanOrEqual(1);
    expect(chair.getByText('✓ Nothing needs you right now.')).toBeInTheDocument();
    chair.unmount();

    mockFetchByUrl(routes);
    const hub = render(<LifeOSHub />);
    expect(await hub.findByText('STEADY TODAY')).toBeInTheDocument();
    expect(hub.getByText('✓ Nothing needs your attention.')).toBeInTheDocument();
    hub.unmount();
  });

  it('agree on UNKNOWN when Human Systems has no check-in today', async () => {
    const routes = {
      '/api/human-systems/context': { ...DEFAULT_HUMAN_SYSTEMS_CONTEXT, posture: 'UNKNOWN', available_capacity: 'unknown', has_checkin_today: false },
    };

    mockFetchByUrl(routes);
    const chair = render(<CaptainsChairWorkbench />);
    expect((await chair.findAllByText(/^UNKNOWN/)).length).toBeGreaterThanOrEqual(1);
    chair.unmount();

    mockFetchByUrl(routes);
    const hub = render(<LifeOSHub />);
    expect(await hub.findByText('UNKNOWN TODAY')).toBeInTheDocument();
    hub.unmount();
  });
});
