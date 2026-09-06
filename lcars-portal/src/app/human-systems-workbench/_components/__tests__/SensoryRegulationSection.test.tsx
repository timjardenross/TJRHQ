// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
// This repo has no global vitest setupFile registering jest-dom matchers
// (toHaveTextContent etc.) — import directly (see WhatHelpsMeCard.test.tsx).
import '@testing-library/jest-dom/vitest';

import { MedicalView } from '../MedicalView';
import type { MedicalPayload } from '../types';

afterEach(cleanup);

// V3 Mission 3 (§10 "Sensory Regulation Upgrade" / §11 "Natural Regulation
// Response") — the "Sensory & Regulation" card should: (1) pair the coarse
// stimulation_state summary with any deeper per-channel breakdown, per the
// doc's own worked example ("Overall stimulation is balanced, but auditory
// load is high"); (2) show natural_regulation.response plainly; (3) show
// the suppressed-response note only when suppressed is explicitly true,
// phrased as compensation-cost learning, never as something to fix
// (V3 doc §3.6/§11); (4) say "Not recorded" rather than fabricate a
// default when a field is null (this is a deep-check-tier, occasionally-
// answered layer, so null is the common case, not an error state).

function basePayload(overrides: Partial<MedicalPayload> = {}): MedicalPayload {
  return {
    domain: 'medical',
    kpis: {
      posture: 'STABLE',
      lp_score: null,
      lp_band: 'unknown',
      sessions_7d: 0,
      capacity_band: 'unknown',
      sleep_hours: null,
      checkins_today: 1,
      latest_capacity_state: 'green',
      has_midday_checkin: false,
      latest_midday_capacity_state: null,
      system_posture: 'STEADY',
    },
    life_participation: {
      score: null,
      band: 'unknown',
      components: { movement: false, pleasure: null, social: false, sitting_minutes: 0, sitting_baseline: 120, workload: 'unknown' },
    },
    capacity_domains: [],
    recovery_conditions: [],
    trends: [],
    capacity_debt: { days_with_debt: 0, days_total: 0, window_days: 7 },
    recovery_duration: { most_common: null, most_common_count: 0, sample_size: 0 },
    intervention_effectiveness: [],
    redesign_candidates: [],
    sensory_profile: { stimulation_state: null, channels: null },
    natural_regulation: { response: null, suppressed: null },
    ...overrides,
  };
}

describe('MedicalView — Sensory & Regulation card (V3 §10/§11)', () => {
  it('shows "Not recorded" for stimulation and natural regulation when nothing is set', () => {
    render(<MedicalView data={basePayload()} />);
    expect(screen.getByText('Sensory & Regulation')).toBeInTheDocument();
    const notRecorded = screen.getAllByText('Not recorded');
    expect(notRecorded.length).toBe(2); // stimulation_state + natural_regulation.response
    expect(screen.getByText('No specific channel recorded as standing out.')).toBeInTheDocument();
  });

  it('pairs the coarse stimulation reading with a per-channel breakdown when channels are recorded', () => {
    render(
      <MedicalView
        data={basePayload({
          sensory_profile: {
            stimulation_state: 'balanced',
            channels: { auditory: 'reduce_avoid', touch: 'seek_helpful' },
          },
        })}
      />,
    );
    expect(screen.getByText('Balanced')).toBeInTheDocument();
    expect(screen.getByText('Auditory')).toBeInTheDocument();
    expect(screen.getByText('Reduce / avoid')).toBeInTheDocument();
    expect(screen.getByText('Touch')).toBeInTheDocument();
    expect(screen.getByText('Seek / helpful')).toBeInTheDocument();
    // the "no channel flagged" fallback must not also render
    expect(screen.queryByText('No specific channel recorded as standing out.')).not.toBeInTheDocument();
  });

  it('shows the natural regulation response label when set', () => {
    render(<MedicalView data={basePayload({ natural_regulation: { response: 'be_alone', suppressed: null } })} />);
    expect(screen.getByText('Be alone')).toBeInTheDocument();
  });

  it('shows the suppressed-response note, phrased as compensation-cost learning, only when suppressed is true', () => {
    render(<MedicalView data={basePayload({ natural_regulation: { response: 'quiet', suppressed: true } })} />);
    expect(screen.getByText(/compensation-cost learning/)).toBeInTheDocument();
    expect(screen.queryByText(/prompt to correct it/)).toBeInTheDocument();
  });

  it('does not show the suppressed-response note when suppressed is false or null', () => {
    const { rerender } = render(
      <MedicalView data={basePayload({ natural_regulation: { response: 'quiet', suppressed: false } })} />,
    );
    expect(screen.queryByText(/compensation-cost learning/)).not.toBeInTheDocument();

    rerender(<MedicalView data={basePayload({ natural_regulation: { response: 'quiet', suppressed: null } })} />);
    expect(screen.queryByText(/compensation-cost learning/)).not.toBeInTheDocument();
  });
});
