// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// 2026-08-29 council follow-up ("fresh look, further holes" — Captain's
// Chair card council): smoke-test the two new Situation Strip badges
// (Emergency Alerts, Background Systems). This page had zero test
// coverage before this session; a full precise mock of every one of its
// ~8 data sources is disproportionate to what's changing here, so the
// hooks this session didn't touch are mocked at the module boundary
// (established convention, see lib/__tests__/decide.test.ts) and only the
// two new hooks' real fetch-driven logic runs.

vi.mock('@/lib/useROSData', () => ({
  useROSData: () => ({ posture: { posture: 'STABLE', capacity_band: null }, postureFetchFailed: false }),
}));
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
  };
});
vi.mock('@/lib/supabase-browser', () => ({
  createSupabaseBrowserClient: () => ({
    from: () => ({
      select: () => ({
        in: () => ({
          order: () => ({
            limit: () => Promise.resolve({ data: [], error: null }),
          }),
        }),
      }),
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

describe('Captain\'s Chair — Situation Strip', () => {
  it('renders without throwing and shows "Clear"/"Nominal" defaults when no emergency alerts or failed jobs exist', async () => {
    mockFetchByUrl({
      '/api/emergency-alerts': { alerts: [] },
      '/api/agent-status': { jobs: [] },
    });

    render(<CaptainsChairWorkbench />);

    expect(await screen.findByText('Emergency Alerts')).toBeInTheDocument();
    expect(await screen.findByText('Background Systems')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Clear')).toBeInTheDocument();
      expect(screen.getByText('Nominal')).toBeInTheDocument();
    });
  });

  it('shows the worst active alert tier and headline when an emergency_warning is active', async () => {
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

    // 2 urgent-tier alerts total (1 watch_and_act + 1 emergency_warning) —
    // count includes both tiers, worst-headline picks emergency_warning first.
    expect(await screen.findByText('2 Active')).toBeInTheDocument();
    expect(await screen.findByText('Emergency warning — Bushfire, Blue Mountains')).toBeInTheDocument();
  });

  it('shows the failing job count and worst job label when a scheduled job has failed', async () => {
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

    expect(await screen.findByText('1 Failing')).toBeInTheDocument();
    expect(await screen.findByText('Downdetector Priority Polling')).toBeInTheDocument();
  });
});
