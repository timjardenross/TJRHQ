// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
// This repo has no global vitest setupFile registering jest-dom matchers
// (toHaveTextContent etc.) — import directly (see DomainToggle.test.tsx).
import '@testing-library/jest-dom/vitest';

import { WhatHelpsMeCard } from '../WhatHelpsMeCard';
import type { InterventionEffectiveness } from '../types';

afterEach(cleanup);

// V3 doc §16 "Evidence Metadata" / §27 language standard: general evidence
// must be shown as a secondary, non-clinical-authority signal, and must be
// suppressed entirely when evidence_strength is 'unknown' — that's the
// default for all 30 originally-seeded capacity_interventions rows
// (migration 0157), so showing an 'unknown' badge on every row would be
// noise, not signal.

function baseRow(overrides: Partial<InterventionEffectiveness> = {}): InterventionEffectiveness {
  return {
    intervention_id: 'move_5',
    title: 'Move for 5-10 minutes',
    attempts: 5,
    better: 3,
    same: 1,
    worse: 1,
    not_completed: 0,
    meets_sample_threshold: true,
    common_context: null,
    evidence_strength: 'unknown',
    evidence_basis: null,
    ...overrides,
  };
}

describe('WhatHelpsMeCard — evidence metadata (V3 §16)', () => {
  it('does not render an evidence badge when evidence_strength is unknown', () => {
    render(<WhatHelpsMeCard data={[baseRow({ evidence_strength: 'unknown' })]} />);
    expect(screen.getByText('Move for 5-10 minutes')).toBeInTheDocument();
    expect(screen.queryByText(/Evidence-informed/)).not.toBeInTheDocument();
  });

  it('renders a secondary evidence badge when evidence_strength is set', () => {
    render(
      <WhatHelpsMeCard
        data={[
          baseRow({
            evidence_strength: 'moderate',
            evidence_basis: 'Some general research summary',
          }),
        ]}
      />,
    );
    expect(screen.getByText(/Evidence-informed · moderate support/)).toBeInTheDocument();
  });

  it('never merges personal effectiveness and general evidence into one figure', () => {
    render(
      <WhatHelpsMeCard
        data={[baseRow({ evidence_strength: 'established_guideline_aligned', better: 4, worse: 0, same: 0 })]}
      />,
    );
    // Personal effectiveness stays in its own Badge (the "4/4 Better" style
    // pill); the evidence label is separate text, never folded into it.
    expect(screen.getByText(/4\/4 Better/)).toBeInTheDocument();
    expect(screen.getByText(/Evidence-informed · guideline-aligned/)).toBeInTheDocument();
  });

  it('renders rows with all-null evidence fields (the 30 pre-existing seeded interventions) without crashing', () => {
    render(
      <WhatHelpsMeCard
        data={[baseRow({ evidence_strength: 'unknown', evidence_basis: null, common_context: null })]}
      />,
    );
    expect(screen.getByText('Move for 5-10 minutes')).toBeInTheDocument();
  });
});
