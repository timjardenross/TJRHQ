// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Command-Experience vNext (Phase 2): the old MSN-0364-era Situation panel
// (Personal/Environment/Systems fold) is gone, replaced by dedicated
// Intelligence/Capacity/System Status sections plus a command-level Today
// headline (commandState.ts's deriveCommandPosture()). These tests are the
// deliberate replacement — same underlying data flows (emergency alerts,
// HQ Status, curated oldest-item), asserted against the new copy/structure.

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
// consumed via useHumanSystemsContext()/`/api/human-systems/context`. A
// fresh, checked-in-today STEADY day by default; individual tests override
// this key in their own routes map when they need a different state.
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

// Canonical HQ Status summary (hqStatusInterpreter.ts's
// buildCaptainChairSummary(), via useHqStatusSummary()/`/api/agent-status-
// workbench/overview`) — normal/healthy by default.
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

function degradedHqStatus(summary: string) {
  return {
    ...DEFAULT_HQ_STATUS,
    posture: 'degraded',
    headline: 'HQ is degraded',
    captainSummary: { ...DEFAULT_HQ_STATUS.captainSummary, hq_posture: 'DEGRADED', summary },
  };
}

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

/** Like mockFetchByUrl, but the /api/human-systems/context response only
 * resolves once the returned `resolve()` is called — lets a test inspect
 * the DOM mid-flight, before that one fetch settles. */
function mockFetchWithDeferredHumanSystems(routes: Record<string, unknown> = {}) {
  let resolveHumanSystems!: (body: unknown) => void;
  const humanSystemsPromise = new Promise<unknown>((resolve) => { resolveHumanSystems = resolve; });
  const merged = { '/api/agent-status-workbench/overview': DEFAULT_HQ_STATUS, ...routes };
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url.startsWith('/api/human-systems/context')) {
      return humanSystemsPromise.then((body) => ({ ok: true, json: async () => body }) as Response);
    }
    for (const [prefix, body] of Object.entries(merged)) {
      if (url.startsWith(prefix)) {
        return Promise.resolve({ ok: true, json: async () => body } as Response);
      }
    }
    return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
  }));
  return { resolveHumanSystems: () => resolveHumanSystems(DEFAULT_HUMAN_SYSTEMS_CONTEXT) };
}

describe('Captain\'s Chair — Today (command posture)', () => {
  it('renders a quiet STEADY day and Nothing-needs-you when every source is quiet', async () => {
    mockFetchByUrl({ '/api/emergency-alerts': { alerts: [] } });

    render(<CaptainsChairWorkbench />);

    // STEADY legitimately renders twice — the Today headline (command
    // posture) and the Capacity section (Human Systems' own posture band),
    // which happen to agree on a quiet day.
    expect((await screen.findAllByText('STEADY')).length).toBeGreaterThanOrEqual(1);
    await waitFor(() => {
      expect(screen.getByText(/normal operating day/i)).toBeInTheDocument();
      expect(screen.getByText('✓ Nothing needs you right now.')).toBeInTheDocument();
    });
    // Drill-down signal chips are preserved even though the old 5-badge strip is gone.
    expect(screen.getByText(/Alerts: Clear/)).toBeInTheDocument();
    expect(screen.getByText(/HQ: NORMAL/)).toBeInTheDocument();
  });

  it('surfaces an emergency_warning as a Needs You safety item, a RESPOND posture, and an urgent-exception flag', async () => {
    mockFetchByUrl({
      '/api/emergency-alerts': {
        alerts: [
          { severity: 'watch_and_act', headline: 'Watch and act — Grassfire near Toowoomba' },
          { severity: 'emergency_warning', headline: 'Emergency warning — Bushfire, Blue Mountains' },
        ],
      },
    });

    render(<CaptainsChairWorkbench />);

    // Emergency overrides calm presentation (mission scenario D) — the
    // command-level headline reads RESPOND, not the quiet-day STEADY.
    expect(await screen.findByText('RESPOND')).toBeInTheDocument();
    expect(screen.getByText('Needs attention now')).toBeInTheDocument();
    // Appears in both Needs You and the Intelligence headline detail —
    // both are legitimate places to surface it.
    expect((await screen.findAllByText('Emergency warning — Bushfire, Blue Mountains')).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Alerts: 2 Active/)).toBeInTheDocument();
  });

  it('treats a merely DEGRADED HQ as a tiny System Status note, never a Needs You item', async () => {
    // Mission scenario E: a machine fails once, self-recovers — no Needs
    // You, no user alert, no false ATTENTION.
    mockFetchByUrl({
      '/api/emergency-alerts': { alerts: [] },
      '/api/agent-status-workbench/overview': degradedHqStatus('HQ is degraded — Morning Brief source coverage is incomplete.'),
    });

    render(<CaptainsChairWorkbench />);

    expect(await screen.findByText(/HQ is degraded/)).toBeInTheDocument();
    expect(screen.getByText('No action required yet.')).toBeInTheDocument();
    expect(screen.getByText('✓ Nothing needs you right now.')).toBeInTheDocument();
    expect(screen.getAllByText('STEADY').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/HQ: DEGRADED/)).toBeInTheDocument();
  });

  it('surfaces a genuine HQ ATTENTION as both a Needs You item and a System Status escalation', async () => {
    // Mission scenario F: genuine HQ intervention required (e.g. Calendar
    // auth expired) — HQ Status ATTENTION, a Needs You item, and a route.
    mockFetchByUrl({
      '/api/emergency-alerts': { alerts: [] },
      '/api/agent-status-workbench/overview': attentionHqStatus('Google Calendar authentication expired', 'Reconnect required.'),
    });

    render(<CaptainsChairWorkbench />);

    expect(await screen.findByText('Google Calendar authentication expired')).toBeInTheDocument();
    expect(screen.getByText('HQ NEEDS YOU')).toBeInTheDocument();
    expect(screen.getByText('RESPOND')).toBeInTheDocument();
  });

  it('surfaces content awaiting publish as a curated oldest-item Needs You card, not just a raw count', async () => {
    mockFetchByUrl({
      '/api/emergency-alerts': { alerts: [] },
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

    // Both the command-level posture (Today) and the Capacity section read UNKNOWN.
    expect(await screen.findAllByText(/^UNKNOWN/)).not.toHaveLength(0);
    expect(screen.queryByText('STEADY')).not.toBeInTheDocument();
    expect(screen.queryByText('ENGAGE')).not.toBeInTheDocument();
    expect(screen.queryByText('FOCUS')).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText(/no check-in today/i).length).toBeGreaterThan(0);
    });
  });

  // Code-review finding on this PR: the Human Systems fetch being in
  // flight (context: null, error: null — indistinguishable by shape from
  // "loaded, no check-in") must not flash the honest "no check-in" state
  // before the real result arrives. commandStatusLoading must include
  // Human Systems' own loading flag, not just opRisk/emergency/hqStatus.
  it('shows Assessing…, not a premature "No check-in", while Human Systems is still loading', async () => {
    const { resolveHumanSystems } = mockFetchWithDeferredHumanSystems({
      '/api/emergency-alerts': { alerts: [] },
    });

    render(<CaptainsChairWorkbench />);

    expect(screen.getByText('Assessing…')).toBeInTheDocument();
    expect(screen.queryByText('No check-in')).not.toBeInTheDocument();
    expect(screen.queryByText(/UNKNOWN/)).not.toBeInTheDocument();
    expect(screen.queryByText('STEADY')).not.toBeInTheDocument();

    resolveHumanSystems();

    expect((await screen.findAllByText('STEADY')).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Capacity: green/)).toBeInTheDocument();
  });
});
