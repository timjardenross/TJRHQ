// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// MSN-0364 Captain's Chair redesign: the 5 equal-weight SituationBadge
// cards this file's original tests asserted on are gone, replaced by one
// interpreted Command Status + a Needs You decision queue. These tests
// are the deliberate replacement (mission doc §8's acceptance criterion),
// not a silent drop — same underlying data flows (emergency alerts, agent
// health, curated oldest-item), asserted against the new copy/structure.

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
        in: () => ({
          order: () => ({
            limit: () => Promise.resolve({ data: [], error: null }),
          }),
        }),
      }),
      insert: () => Promise.resolve({ error: null }),
    }),
  }),
}));
vi.mock('@/components/TodaysBriefPanel', () => ({
  TodaysBriefPanel: () => null,
}));
// WorkbenchShell's persistent workbench switcher calls useRouter/usePathname
// - no app router is mounted in this harness either (see a11y.test.tsx).
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: () => {}, replace: () => {} }),
  usePathname: () => '/captains-chair-workbench',
}));

import CaptainsChairWorkbench from '../page';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// Canonical Human Systems assessed context (assessed-context.ts) —
// consumed via useHumanSystemsContext()/`/api/human-systems/context`
// since the P0 correctness repair replaced useROSData()'s mock-fallback
// posture on this page. A fresh, checked-in-today STEADY day by default;
// individual tests override this key in their own routes map when they
// need a different Human Systems state.
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

function mockFetchByUrl(routes: Record<string, unknown>) {
  const merged = { '/api/human-systems/context': DEFAULT_HUMAN_SYSTEMS_CONTEXT, ...routes };
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

/** Like mockFetchByUrl, but the /api/human-systems/context response only
 * resolves once the returned `resolve()` is called — lets a test inspect
 * the DOM mid-flight, before that one fetch settles. */
function mockFetchWithDeferredHumanSystems(routes: Record<string, unknown> = {}) {
  let resolveHumanSystems!: (body: unknown) => void;
  const humanSystemsPromise = new Promise<unknown>((resolve) => { resolveHumanSystems = resolve; });
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url.startsWith('/api/human-systems/context')) {
      return humanSystemsPromise.then((body) => ({ ok: true, json: async () => body }) as Response);
    }
    for (const [prefix, body] of Object.entries(routes)) {
      if (url.startsWith(prefix)) {
        return Promise.resolve({ ok: true, json: async () => body } as Response);
      }
    }
    return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
  }));
  return { resolveHumanSystems: () => resolveHumanSystems(DEFAULT_HUMAN_SYSTEMS_CONTEXT) };
}

describe('Captain\'s Chair — Command Status', () => {
  it('renders a stable interpretation and Nothing-needs-you when every source is quiet', async () => {
    mockFetchByUrl({
      '/api/emergency-alerts': { alerts: [] },
      '/api/agent-status': { jobs: [] },
    });

    render(<CaptainsChairWorkbench />);

    expect(await screen.findByText('STEADY')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/both stable/i)).toBeInTheDocument();
      expect(screen.getByText('✓ Nothing needs you right now.')).toBeInTheDocument();
    });
    // Drill-down signal chips are preserved even though the 5-badge strip is gone.
    expect(screen.getByText(/Alerts: Clear/)).toBeInTheDocument();
    expect(screen.getByText(/Systems: Nominal/)).toBeInTheDocument();
  });

  it('surfaces an emergency_warning as a Needs You safety item and an urgent-exception flag', async () => {
    mockFetchByUrl({
      '/api/emergency-alerts': {
        alerts: [
          { severity: 'watch_and_act', headline: 'Watch and act — Grassfire near Toowoomba' },
          { severity: 'emergency_warning', headline: 'Emergency warning — Bushfire, Blue Mountains' },
        ],
      },
      '/api/agent-status': { jobs: [] },
    });

    render(<CaptainsChairWorkbench />);

    expect(await screen.findByText('Needs attention now')).toBeInTheDocument();
    // Appears in both Needs You and Situation — both are legitimate places
    // to surface it, so assert presence rather than uniqueness.
    await waitFor(() => {
      expect(screen.getAllByText('Emergency warning — Bushfire, Blue Mountains').length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/Alerts: 2 Active/)).toBeInTheDocument();
  });

  it('surfaces a failing job as a Systems chip, not a full-page red state', async () => {
    mockFetchByUrl({
      '/api/emergency-alerts': { alerts: [] },
      '/api/agent-status': {
        jobs: [
          { status: 'ok', label: 'Morning Brief' },
          { status: 'failed', label: 'Downdetector Priority Polling' },
        ],
      },
    });

    render(<CaptainsChairWorkbench />);

    expect(await screen.findByText(/Systems: 1 Failing/)).toBeInTheDocument();
  });

  it('surfaces content awaiting publish as a curated oldest-item Needs You card, not just a raw count', async () => {
    mockFetchByUrl({
      '/api/emergency-alerts': { alerts: [] },
      '/api/agent-status': { jobs: [] },
      '/api/content-workbench': {
        items: [
          { status: 'ready_to_publish', title: 'Newer draft — AI regulation roundup', created_at: '2026-08-20T00:00:00Z' },
          { status: 'ready_to_publish', title: 'Older draft — Quarterly platform update', created_at: '2026-08-10T00:00:00Z' },
          { status: 'draft', title: 'Not awaiting publish', created_at: '2026-08-01T00:00:00Z' },
        ],
      },
    });
    mockInboxCaptures.mockResolvedValueOnce([
      { title: null, raw_text: 'A voice memo with no title, captured a while ago' },
    ]);
    mockCaptureAnalytics.mockResolvedValueOnce({ today: 0, this_week: 1, pending: 1, by_source: {}, by_classification: {} });

    render(<CaptainsChairWorkbench />);

    // Oldest ready_to_publish item (by created_at), not the newest.
    expect(await screen.findByText('Older draft — Quarterly platform update')).toBeInTheDocument();
    expect(screen.queryByText('Newer draft — AI regulation roundup')).not.toBeInTheDocument();

    // Falls back to a raw_text excerpt when a capture has no title.
    expect(await screen.findByText('A voice memo with no title, captured a while ago')).toBeInTheDocument();
  });

  // Command-Experience correctness repair, P0 test scenario A: a day with
  // no Human Systems check-in must never render a fabricated posture band.
  it('never fabricates a posture when Human Systems has no check-in today', async () => {
    mockFetchByUrl({
      '/api/emergency-alerts': { alerts: [] },
      '/api/agent-status': { jobs: [] },
      '/api/human-systems/context': {
        ...DEFAULT_HUMAN_SYSTEMS_CONTEXT,
        posture: 'UNKNOWN',
        posture_message: 'No capacity check-in recorded for today yet.',
        available_capacity: 'unknown',
        freshness: { status: 'none', last_checkin_at: null },
        confidence: 'low',
        has_checkin_today: false,
      },
    });

    render(<CaptainsChairWorkbench />);

    expect(await screen.findByText(/^UNKNOWN/)).toBeInTheDocument();
    expect(screen.queryByText('STEADY')).not.toBeInTheDocument();
    expect(screen.queryByText('ENGAGE')).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText(/no check-in today/i).length).toBeGreaterThan(0);
    });
  });

  // Code-review finding on this PR: the Human Systems fetch being in
  // flight (context: null, error: null — indistinguishable by shape from
  // "loaded, no check-in") must not flash the honest "no check-in" state
  // before the real result arrives. commandStatusLoading must include
  // Human Systems' own loading flag, not just opRisk/emergency/agentHealth.
  it('shows Assessing…, not a premature "No check-in", while Human Systems is still loading', async () => {
    const { resolveHumanSystems } = mockFetchWithDeferredHumanSystems({
      '/api/emergency-alerts': { alerts: [] },
      '/api/agent-status': { jobs: [] },
    });

    render(<CaptainsChairWorkbench />);

    expect(screen.getByText('Assessing…')).toBeInTheDocument();
    expect(screen.queryByText('No check-in')).not.toBeInTheDocument();
    expect(screen.queryByText(/UNKNOWN/)).not.toBeInTheDocument();
    expect(screen.queryByText('STEADY')).not.toBeInTheDocument();

    resolveHumanSystems();

    expect(await screen.findByText('STEADY')).toBeInTheDocument();
    expect(screen.getByText(/Capacity: green/)).toBeInTheDocument();
  });
});
