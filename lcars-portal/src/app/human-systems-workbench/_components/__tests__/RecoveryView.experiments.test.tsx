// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
// This repo has no global vitest setupFile registering jest-dom matchers
// (toHaveTextContent etc.) — import directly (see WhatHelpsMeCard.test.tsx).
import '@testing-library/jest-dom/vitest';

import { RecoveryView } from '../RecoveryView';
import type { CapacityExperiment, RecoveryPayload } from '../types';

afterEach(cleanup);

// V3 Mission 4 (§15/§19) — "Worth Testing" should show the structured
// experiment object once one exists (proposed/active), and must fall back
// to the old worthTesting() narrative heuristic (V3 Rule F: don't
// fabricate structure where there isn't any) when data.experiments is
// empty. "What Changed" (§19's fourth System Learning layer) should only
// appear once a completed/stopped experiment actually has a result.

function experiment(overrides: Partial<CapacityExperiment> = {}): CapacityExperiment {
  return {
    id: 1,
    hypothesis: 'Using a quieter work location before afternoon overload may reduce post-work recovery cost.',
    target_condition: 'Office auditory load',
    proposed_change: 'Use the quiet room before overload for two weeks.',
    baseline_window: '4 of 5 office afternoons reached Stretched or Depleted.',
    trial_window: 'Two weeks',
    outcome_measures: ['3pm capacity', 'sensory load'],
    status: 'proposed',
    result: null,
    confidence: null,
    notes: null,
    started_at: null,
    completed_at: null,
    ...overrides,
  };
}

function basePayload(overrides: Partial<RecoveryPayload> = {}): RecoveryPayload {
  return {
    domain: 'recovery',
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
    posture: 'STABLE',
    posture_message: '',
    capacity_band: 'unknown',
    capacity_message: '',
    mission_guidance: '',
    best_window: '',
    sleep_hours: null,
    sleep_quality: null,
    nervous_system: null,
    energy: null,
    checkins_today: 1,
    latest_capacity_state: 'green',
    latest_regulation_state: null,
    confidence_label: '',
    wellness: { narrative: null, risk_flags: [], positive_flags: [], wins: [], insight_date: null },
    data_available: true,
    system_posture: 'STEADY',
    system_posture_message: 'Maintain current pace.',
    stimulation_state: null,
    pain_state: null,
    pain_score: null,
    executive_function: null,
    compensation_load: null,
    capacity_balance: 'sustainable',
    active_loads_today: [{ label: 'Sensory input', count: 1 }],
    identified_needs_latest: [],
    next_move: {
      lever: null, intervention_title: null, intervention_description: null,
      event_id: null, event_source: null, accepted_at: null, outcome: null,
    },
    checkins_last_7d: 3,
    system_trajectory: 'stable',
    trajectory_confidence: 'moderate',
    strategic_posture: 'steady',
    strategic_posture_message: 'Holding steady.',
    current_recovery_stage: null,
    user_burnout_framing: null,
    experiments: [],
    ...overrides,
  };
}

describe('RecoveryView — Worth Testing / What Changed (V3 §15/§19)', () => {
  it('falls back to the narrative worthTesting() heuristic when there are no structured experiments', () => {
    render(<RecoveryView data={basePayload()} interventionEffectiveness={[]} />);
    // active_loads_today[0].count is 1, below worthTesting()'s own >=2
    // threshold, so with count=1 no narrative renders either — assert the
    // structured card is simply absent, not a specific string.
    expect(screen.queryByText(/Trying —/)).not.toBeInTheDocument();
  });

  it('shows the narrative fallback text when a load has repeated today and no experiment exists', () => {
    render(
      <RecoveryView
        data={basePayload({ active_loads_today: [{ label: 'Sensory input', count: 2 }] })}
        interventionEffectiveness={[]}
      />,
    );
    expect(screen.getByText(/Sensory input has come up in 2 check-ins today/)).toBeInTheDocument();
  });

  it('renders the structured experiment card instead of the narrative fallback when a proposed experiment exists', () => {
    render(
      <RecoveryView
        data={basePayload({
          active_loads_today: [{ label: 'Sensory input', count: 2 }],
          experiments: [experiment({ status: 'proposed' })],
        })}
        interventionEffectiveness={[]}
      />,
    );
    expect(screen.getByText(/Using a quieter work location/)).toBeInTheDocument();
    expect(screen.getByText(/Use the quiet room before overload/)).toBeInTheDocument();
    expect(screen.getByText('3pm capacity')).toBeInTheDocument();
    expect(screen.getByText('Worth testing')).toBeInTheDocument();
    // narrative fallback must not also render
    expect(screen.queryByText(/has come up in 2 check-ins today/)).not.toBeInTheDocument();
  });

  it('labels an active experiment "In progress" rather than "Worth testing"', () => {
    render(
      <RecoveryView
        data={basePayload({ experiments: [experiment({ status: 'active', started_at: '2026-08-10T09:00:00Z' })] })}
        interventionEffectiveness={[]}
      />,
    );
    expect(screen.getByText('In progress')).toBeInTheDocument();
  });

  it('never frames the experiment as a commitment — copy stays reversible/stoppable', () => {
    render(
      <RecoveryView data={basePayload({ experiments: [experiment({ status: 'active' })] })} interventionEffectiveness={[]} />,
    );
    expect(screen.getByText(/stop it anytime/i)).toBeInTheDocument();
  });

  it('shows "What Changed" once a completed experiment has a result', () => {
    render(
      <RecoveryView
        data={basePayload({
          experiments: [
            experiment({
              status: 'completed',
              result: 'Post-work recovery cost was noticeably lower on quiet-room afternoons.',
              confidence: 'moderate',
              completed_at: '2026-08-20T00:00:00Z',
            }),
          ],
        })}
        interventionEffectiveness={[]}
      />,
    );
    expect(screen.getByText('What Changed')).toBeInTheDocument();
    expect(screen.getByText(/Post-work recovery cost was noticeably lower/)).toBeInTheDocument();
    expect(screen.getByText(/Confidence — moderate/)).toBeInTheDocument();
  });

  it('does not show "What Changed" for a completed experiment with no result yet', () => {
    render(
      <RecoveryView
        data={basePayload({ experiments: [experiment({ status: 'completed', result: null })] })}
        interventionEffectiveness={[]}
      />,
    );
    expect(screen.queryByText('What Changed')).not.toBeInTheDocument();
  });

  it('renders both an active experiment card and a separate finished What Changed entry without crashing', () => {
    render(
      <RecoveryView
        data={basePayload({
          experiments: [
            experiment({ id: 2, status: 'active', hypothesis: 'New hypothesis in progress' }),
            experiment({
              id: 1, status: 'stopped', hypothesis: 'Old hypothesis',
              result: 'Made evenings worse, stopped after 4 days.', confidence: 'low',
            }),
          ],
        })}
        interventionEffectiveness={[]}
      />,
    );
    expect(screen.getByText('New hypothesis in progress')).toBeInTheDocument();
    expect(screen.getByText('Old hypothesis')).toBeInTheDocument();
    expect(screen.getByText(/Made evenings worse/)).toBeInTheDocument();
  });
});
