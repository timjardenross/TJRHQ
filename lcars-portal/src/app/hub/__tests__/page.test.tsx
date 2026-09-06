// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Command-Experience vNext (Phase 2): LifeOS Hub used to render a permanent
// 5-badge situation strip (Recovery Posture/Operational Risk/Interrupt Now/
// Emergency Alerts/Background Systems) plus a raw Live Alerts list — the
// "dashboard, not command system" pattern the mission calls out. These
// tests assert the replacement: one command-posture headline, a curated
// Needs You list identical to Captain's Chair's, and Sanctuary/quiet-mode
// behaviour when capacity is constrained and nothing needs attention.

vi.mock('@/lib/useAlerts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/useAlerts')>();
  return {
    ...actual,
    useAlerts: () => ({ alerts: [], isLoading: false, failedSources: 0, totalSources: 6 }),
    useAlertCount: () => 0,
  };
});
const mockInboxCaptures = vi.fn(async () => [] as { title: string | null; raw_text: string | null }[]);
const mockCaptureAnalytics = vi.fn(async () => ({ today: 0, this_week: 0, pending: 0, by_source: {}, by_classification: {} }));
vi.mock('@/lib/capture', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/capture')>();
  return {
    ...actual,
    fetchCaptureAnalytics: () => mockCaptureAnalytics(),
    fetchInboxCaptures: (...args: unknown[]) => mockInboxCaptures(...(args as [])),
  };
});
vi.mock('@/lib/supabase-browser', () => ({
  createSupabaseBrowserClient: () => ({
    from: () => ({
      select: () => ({
        eq: () => Promise.resolve({ data: [], error: null }),
      }),
    }),
  }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: () => {}, replace: () => {} }),
  usePathname: () => '/hub',
}));

import LifeOSHub from '../page';

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

function mockFetchByUrl(routes: Record<string, unknown>) {
  const merged = {
    '/api/human-systems/context': DEFAULT_HUMAN_SYSTEMS_CONTEXT,
    '/api/agent-status-workbench/overview': DEFAULT_HQ_STATUS,
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

describe('LifeOS Hub — command picture', () => {
  it('is quiet on a normal day: STEADY headline, nothing needs you, calm end state', async () => {
    mockFetchByUrl({ '/api/emergency-alerts': { alerts: [] } });

    render(<LifeOSHub />);

    expect(await screen.findByText('STEADY TODAY')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('✓ Nothing needs your attention.')).toBeInTheDocument();
      expect(screen.getByText('Nothing else needs you.')).toBeInTheDocument();
    });
  });

  it('agrees with Captain\'s Chair: an emergency_warning overrides calm presentation with RESPOND', async () => {
    mockFetchByUrl({
      '/api/emergency-alerts': {
        alerts: [{ severity: 'emergency_warning', headline: 'Emergency warning — Bushfire, Blue Mountains' }],
      },
    });

    render(<LifeOSHub />);

    expect(await screen.findByText('RESPOND TODAY')).toBeInTheDocument();
    // Appears in both Needs You and the World/intelligence detail.
    expect(screen.getAllByText('Emergency warning — Bushfire, Blue Mountains').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('Nothing else needs you.')).not.toBeInTheDocument();
  });

  it('never fabricates a posture when Human Systems has no check-in today', async () => {
    mockFetchByUrl({
      '/api/emergency-alerts': { alerts: [] },
      '/api/human-systems/context': {
        ...DEFAULT_HUMAN_SYSTEMS_CONTEXT,
        posture: 'UNKNOWN',
        posture_message: 'No capacity check-in recorded for today yet.',
        available_capacity: 'unknown',
        has_checkin_today: false,
      },
    });

    render(<LifeOSHub />);

    expect(await screen.findByText('UNKNOWN TODAY')).toBeInTheDocument();
    expect(screen.queryByText('STEADY TODAY')).not.toBeInTheDocument();
  });

  it('quiets itself (Sanctuary) when capacity is constrained and nothing needs attention', async () => {
    mockFetchByUrl({
      '/api/emergency-alerts': { alerts: [] },
      '/api/human-systems/context': { ...DEFAULT_HUMAN_SYSTEMS_CONTEXT, posture: 'PROTECT', available_capacity: 'orange' },
    });

    render(<LifeOSHub />);

    expect(await screen.findByText('PROTECT TODAY')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('✓ Nothing needs your attention.')).toBeInTheDocument();
    });
    // Next commitments and World sections quiet themselves — never Needs You.
    expect(screen.queryByText('Next')).not.toBeInTheDocument();
    expect(screen.queryByText('World')).not.toBeInTheDocument();
    expect(screen.getByText('Needs You')).toBeInTheDocument();
  });

  // Acceptance-audit repair: Sanctuary previously gated the entire World
  // section on posture + Needs You alone. hasEnvironmentConcern only
  // reacts to emergency_warning/RED, not a lesser watch_and_act tier — so
  // PROTECT + zero Needs You could coexist with a genuinely-material
  // intelligence signal, and quiet mode would silently hide it. Quiet mode
  // must change presentation, never truth.
  it('does not hide a material World/Intelligence signal behind Sanctuary quiet mode', async () => {
    mockFetchByUrl({
      '/api/emergency-alerts': { alerts: [{ severity: 'watch_and_act', headline: 'Grassfire watch — regional area' }] },
      '/api/human-systems/context': { ...DEFAULT_HUMAN_SYSTEMS_CONTEXT, posture: 'PROTECT', available_capacity: 'orange' },
    });

    render(<LifeOSHub />);

    expect(await screen.findByText('PROTECT TODAY')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('✓ Nothing needs your attention.')).toBeInTheDocument();
    });
    // Next (calendar) may still quiet itself — it's discretionary, not risk.
    expect(screen.queryByText('Next')).not.toBeInTheDocument();
    // World must NOT disappear: a watch_and_act tier is material.
    expect(screen.getByText('World')).toBeInTheDocument();
    expect(screen.getByText(/ITEM ON WATCH/)).toBeInTheDocument();
  });

  // Test scenario per the acceptance audit: absence of evidence must never
  // become evidence that everything is fine. Human Systems unavailable,
  // Brief unavailable, and Calendar disconnected simultaneously.
  it('never synthesizes a reassuring normal day from absence of evidence', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.startsWith('/api/human-systems/context')) return Promise.resolve({ ok: false, status: 500, json: async () => ({}) } as Response);
      if (url.startsWith('/api/captain-brief')) return Promise.resolve({ ok: false, status: 500, json: async () => ({}) } as Response);
      if (url.startsWith('/api/calendar/today')) return Promise.resolve({ ok: true, json: async () => ({ status: 'disconnected' }) } as Response);
      if (url.startsWith('/api/emergency-alerts')) return Promise.resolve({ ok: true, json: async () => ({ alerts: [] }) } as Response);
      if (url.startsWith('/api/agent-status-workbench/overview')) return Promise.resolve({ ok: true, json: async () => DEFAULT_HQ_STATUS } as Response);
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
    }));

    render(<LifeOSHub />);

    expect(await screen.findByText('UNKNOWN TODAY')).toBeInTheDocument();
    expect(screen.queryByText('STEADY TODAY')).not.toBeInTheDocument();
    expect(screen.queryByText('FOCUS TODAY')).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/INTELLIGENCE UNAVAILABLE/)).toBeInTheDocument();
      expect(screen.getByText(/Calendar isn.t connected/)).toBeInTheDocument();
    });
  });
});
