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

vi.mock('@/lib/useROSData', () => ({
  useROSData: () => ({
    posture: { posture: 'STABLE', capacity_band: 'GOOD', posture_message: '', capacity_message: '', best_window: '', mission_guidance: '', data_available: true },
    postureFetchFailed: false,
  }),
}));
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

function mockFetchByUrl(routes: Record<string, unknown>) {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    for (const [prefix, body] of Object.entries(routes)) {
      if (url.startsWith(prefix)) {
        return Promise.resolve({ ok: true, json: async () => body } as Response);
      }
    }
    return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
  }));
}

describe('Captain\'s Chair — Command Status', () => {
  it('renders a stable interpretation and Nothing-needs-you when every source is quiet', async () => {
    mockFetchByUrl({
      '/api/emergency-alerts': { alerts: [] },
      '/api/agent-status': { jobs: [] },
    });

    render(<CaptainsChairWorkbench />);

    expect(await screen.findByText('STABLE')).toBeInTheDocument();
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
});
