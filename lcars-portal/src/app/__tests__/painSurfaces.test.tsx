// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Phase 2 step 1 (R2 alignment): every surface that used to print a raw
// "n/10" pain value now shows pain "compared with your usual baseline" for
// new data, labels an old numeric value as history, and shows nothing — never
// 0 or "no pain" — when no value was recorded. One test per case per surface.

let checkinRows: Record<string, unknown>[] = [];

vi.mock('@/lib/supabase-browser', () => {
  const makeChain = (table: string) => {
    const rows = table === 'capacity_checkins' ? checkinRows : [];
    const chain: Record<string, unknown> = new Proxy({}, {
      get: (_t, prop) => {
        if (prop === 'then') return (res: (v: unknown) => unknown) => res({ data: rows, error: null, count: 0 });
        if (prop === 'maybeSingle' || prop === 'single') {
          return () => Promise.resolve({ data: rows[0] ?? null, error: null });
        }
        return () => chain;
      },
    });
    return chain;
  };
  return { createSupabaseBrowserClient: () => ({ from: (t: string) => makeChain(t), rpc: () => makeChain('rpc') }) };
});

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: () => {}, replace: () => {} }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));

import RecoveryPulsePage from '../human-systems-workbench/medical/pulse/page';
import CheckInPage from '../human-systems-workbench/medical/check-in/page';
import OperatingModelPage from '../knowledge-workbench/operating-model/page';
import TimelinePage from '../timeline/page';
import { CapacityTodayCard, WhatIsDrivingItCard } from '../human-systems-workbench/_components/RecoveryView';
import { PAIN_STATE_LABEL } from '../human-systems-workbench/_components/types';
import type { RecoveryPayload } from '../human-systems-workbench/_components/types';

afterEach(() => {
  cleanup();
  checkinRows = [];
});

const base = { captured_at: '2026-10-12T10:00:00Z', log_date: '2026-10-12', checkin_type: 'capacity', capacity_state: 'green', regulation_state: 'settled' };
const OLD = { ...base, pain_score: 6, pain_state: null };
const NEW = { ...base, pain_score: null, pain_state: 'elevated' };
const MISSING = { ...base, pain_score: null, pain_state: null };

describe.each([
  ['medical/pulse', RecoveryPulsePage],
  ['medical/check-in', CheckInPage],
])('%s page', (_name, Page) => {
  it('old numeric value is labelled as history', async () => {
    checkinRows = [OLD];
    render(<Page />);
    expect(await screen.findByText('Older 0–10 record: 6/10')).toBeInTheDocument();
  });
  it('new state shows the baseline wording and no number', async () => {
    checkinRows = [NEW];
    render(<Page />);
    expect(await screen.findByText('Higher than usual')).toBeInTheDocument();
    expect(screen.queryByText(/\/10/)).not.toBeInTheDocument();
  });
  it('missing value reads "Not recorded", not 0', async () => {
    checkinRows = [MISSING];
    render(<Page />);
    await waitFor(() => expect(screen.getByText('Pain').nextElementSibling).toHaveTextContent('Not recorded'));
    expect(screen.queryByText(/\/10/)).not.toBeInTheDocument();
  });
});

describe('operating-model page', () => {
  it('old numeric value is labelled as history', async () => {
    checkinRows = [OLD];
    render(<OperatingModelPage />);
    expect(await screen.findByText('Older 0–10 record: 6/10')).toBeInTheDocument();
  });
  it('new state shows the baseline wording and no number', async () => {
    checkinRows = [NEW];
    render(<OperatingModelPage />);
    expect(await screen.findByText('Higher than usual')).toBeInTheDocument();
    expect(screen.queryByText(/\/10/)).not.toBeInTheDocument();
  });
  it('missing value reads as a dash, not 0', async () => {
    checkinRows = [MISSING];
    render(<OperatingModelPage />);
    await waitFor(() => expect(screen.getByText('Pain').nextElementSibling).toHaveTextContent('—'));
    expect(screen.queryByText(/\/10/)).not.toBeInTheDocument();
  });
});

describe('timeline page', () => {
  it('old numeric value is labelled as history', async () => {
    checkinRows = [OLD];
    render(<TimelinePage />);
    expect(await screen.findByText(/pain: Older 0–10 record: 6\/10/)).toBeInTheDocument();
  });
  it('new state shows the baseline wording and no number', async () => {
    checkinRows = [NEW];
    render(<TimelinePage />);
    expect(await screen.findByText(/pain: Higher than usual/)).toBeInTheDocument();
    expect(screen.queryByText(/\/10/)).not.toBeInTheDocument();
  });
  it('missing value adds no pain wording at all', async () => {
    checkinRows = [MISSING];
    render(<TimelinePage />);
    expect(await screen.findByText(/capacity green/)).toBeInTheDocument();
    expect(screen.queryByText(/pain/i)).not.toBeInTheDocument();
  });
});

const payload = (over: Partial<RecoveryPayload>): RecoveryPayload => ({
  data_available: true,
  latest_capacity_state: 'green',
  system_posture_message: 'ok',
  stimulation_state: null,
  pain_state: null,
  pain_score: null,
  executive_function: null,
  compensation_load: null,
  latest_regulation_state: null,
  active_loads_today: [],
  checkins_today: 1,
  ...over,
} as unknown as RecoveryPayload);

describe('RecoveryView', () => {
  it('old numeric value is labelled as history', () => {
    render(<CapacityTodayCard data={payload({ pain_score: 6 })} />);
    expect(screen.getByText('Older 0–10 record: 6/10')).toBeInTheDocument();
  });
  it('new state shows the baseline wording and no number', () => {
    render(<CapacityTodayCard data={payload({ pain_state: 'baseline' })} />);
    expect(screen.getByText('Around usual')).toBeInTheDocument();
    expect(screen.queryByText(/\/10/)).not.toBeInTheDocument();
  });
  it('state plus old number appends the number as history', () => {
    render(<CapacityTodayCard data={payload({ pain_state: 'high', pain_score: 9 })} />);
    expect(screen.getByText('Much higher than usual (older 0–10 record: 9/10)')).toBeInTheDocument();
  });
  it('missing value renders no pain value (and never 0)', () => {
    render(<CapacityTodayCard data={payload({})} />);
    expect(screen.queryByText(/\/10/)).not.toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });
  it('"Pain in Context" note uses baseline wording, with the old number as history', () => {
    render(<WhatIsDrivingItCard data={payload({ pain_state: 'high', pain_score: 9 })} />);
    expect(screen.getByText(/Pain compared with your usual baseline today: Much higher than usual \(older 0–10 record: 9\/10\)/)).toBeInTheDocument();
  });
});

describe('trends labels', () => {
  it('pain-state trend labels use the approved wording', () => {
    expect(PAIN_STATE_LABEL).toEqual({
      low: 'Lower than usual', baseline: 'Around usual', elevated: 'Higher than usual', high: 'Much higher than usual',
    });
  });
});
