// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

import { GoodDaysCard } from '../GoodDaysCard';
import { DayPlanCard } from '../DayPlanCard';
import type { GoodDaysPayload } from '@/app/api/human-systems/good-days-data';
import type { RecoveryPayload } from '../types';

afterEach(cleanup);

const days = (verdicts: (boolean | null)[]) =>
  verdicts.map((verdict, i) => ({ date: `2026-11-0${i + 1}`, zone: i === 0 ? 'orange' : null, verdict }));

function payload(over: Partial<GoodDaysPayload> = {}): GoodDaysPayload {
  return {
    window_days: 3,
    summary: { judged: 3, good: 2, longest_run: 2 },
    days: days([true, true, false]),
    latest_evening: { log_date: '2026-11-03', day_trajectory: 'same', day_compensation_load: 'moderate', good_day: 'kind_of' },
    ...over,
  };
}

describe('GoodDaysCard', () => {
  it('shows the count, the longest run and one timeline entry per day', () => {
    render(<GoodDaysCard data={payload()} error={null} />);
    expect(screen.getByText('2 of 3')).toBeInTheDocument();
    expect(screen.getByText(/longest run 2 days/)).toBeInTheDocument();
    const list = screen.getByRole('list', { name: /good days, last 3 days/i });
    expect(within(list).getAllByRole('listitem')).toHaveLength(3);
    expect(within(list).getAllByRole('listitem')[0]).toHaveAccessibleName(/good day, Stretched/);
    expect(within(list).getAllByRole('listitem')[2]).toHaveAccessibleName(/not a good day/);
  });

  it("shows the latest evening's whole-day answers in plain words", () => {
    render(<GoodDaysCard data={payload()} error={null} />);
    expect(screen.getByText(/About the same · whole-day pushing\/masking: Some · you called it a good day: Kind of/)).toBeInTheDocument();
  });

  it('is calm with no evenings yet, and shows loading and error states', () => {
    const { rerender } = render(
      <GoodDaysCard data={payload({ summary: { judged: 0, good: 0, longest_run: 0 }, latest_evening: null })} error={null} />,
    );
    expect(screen.getByText(/No evenings logged in the last 3 days yet/)).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
    rerender(<GoodDaysCard data={null} error={null} />);
    expect(screen.getByText('Loading…')).toBeInTheDocument();
    rerender(<GoodDaysCard data={null} error="good_days_read_failed" />);
    expect(screen.getByText(/Couldn.t load good days: good_days_read_failed/)).toBeInTheDocument();
  });
});

function recovery(over: Partial<RecoveryPayload> = {}): RecoveryPayload {
  return {
    data_available: true, latest_capacity_state: 'orange', pain_state: 'elevated', executive_function: 'strained',
    compensation_load: 'moderate', latest_regulation_state: 'settled', stimulation_state: 'balanced', ...over,
  } as RecoveryPayload;
}

describe('DayPlanCard', () => {
  it('shows the zone with reasons and the zone prompt, as suggestions only', () => {
    render(<DayPlanCard data={recovery()} />);
    expect(screen.getByText(/Stretched/)).toBeInTheDocument();
    expect(screen.getByText(/pain is above your usual; thinking and deciding is taking more effort/)).toBeInTheDocument();
    expect(screen.getByText(/reduce, regulate or change before this becomes red/)).toBeInTheDocument();
    expect(screen.getByText(/nothing is held back/i)).toBeInTheDocument();
    expect(screen.getByText(/send \/capacity or \/helpme in Telegram/)).toBeInTheDocument();
  });

  it('renders nothing without a capacity answer or check-in data', () => {
    const { container, rerender } = render(<DayPlanCard data={recovery({ latest_capacity_state: null })} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<DayPlanCard data={recovery({ data_available: false })} />);
    expect(container).toBeEmptyDOMElement();
  });
});
