// @vitest-environment jsdom
//
// Briefs/Captain's Brief consolidation — signal-leakage sweep.
//
// PR #275 added `core_events.description` / `CaptainBriefItem.description`
// so a genuine readable event description (a headline, a state transition)
// never has to masquerade as `recommended_action` and never has to fall back
// to `reason` (the Attention Engine's bare scoring trace, e.g.
// "importance=90 >= 75 AND confidence=80 >= 70"). `interrupt_dispatcher.py`
// was fixed to prefer recommendation.description, then description, then
// reason — but this frontend's ItemRow/BriefView never picked up the new
// `description` field, so a description-only item (recommendation is null,
// per the Phase 1 fix) fell straight through to `reason`, reproducing the
// exact anti-pattern one layer up: a scoring formula rendered as the
// headline of a Captain Brief item. These tests pin the three-tier fallback
// (recommendation.description -> description -> reason) so it can't
// regress silently.

import { afterEach, describe, expect, it } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ItemRow } from '../ItemRow';
import { BriefView } from '../BriefView';
import type { CaptainBriefDocument, CaptainBriefItem } from '../types';

afterEach(cleanup);

function item(overrides: Partial<CaptainBriefItem>): CaptainBriefItem {
  return {
    event_id: 'evt-1',
    domain: 'engineering',
    event_type: 'service_state_change',
    category: 'INTERRUPT_NOW',
    reason: 'importance=90 >= 75 AND confidence=80 >= 70',
    priority_score: null,
    priority_explanation: null,
    risk_score: null,
    recommendation: null,
    related_event_ids: [],
    aggregation_key: null,
    description: null,
    ...overrides,
  };
}

describe('ItemRow — headline fallback order', () => {
  it('prefers recommendation.description when a recommendation exists', () => {
    render(
      <ItemRow
        item={item({
          description: 'nginx: failed',
          recommendation: {
            description: 'Restart nginx and check upstream health',
            action_type: 'remediate',
            confidence: 80,
            evidence: [],
            requires_approval: false,
            supporting_context: null,
          },
        })}
      />
    );
    expect(screen.getByText('Restart nginx and check upstream health')).toBeInTheDocument();
    expect(screen.queryByText('nginx: failed')).not.toBeInTheDocument();
  });

  it('uses description, not reason, as the primary headline when there is no recommendation', () => {
    // Mirrors the Phase 1 fix: a systemd state transition / headline / error
    // now lands in `description`, and `recommended_action` (-> recommendation)
    // stays unset, so recommendation_from_event() correctly returns None.
    // `reason` may still render as a demoted secondary caption (unchanged,
    // pre-existing behavior for the recommendation case) — what must never
    // happen is the scoring trace becoming the PRIMARY line.
    render(<ItemRow item={item({ description: 'nginx: failed', recommendation: null })} />);
    const headline = screen.getByText('nginx: failed');
    expect(headline).toBeInTheDocument();
    expect(headline.className).toContain('text-wb-ink/90');
  });

  it('falls back to reason only as a last resort, when neither exists', () => {
    render(<ItemRow item={item({ description: null, recommendation: null })} />);
    expect(screen.getByText('importance=90 >= 75 AND confidence=80 >= 70')).toBeInTheDocument();
  });

  it('does not duplicate the headline as a caption when reason was used as the headline', () => {
    render(<ItemRow item={item({ description: null, recommendation: null })} />);
    expect(screen.getAllByText('importance=90 >= 75 AND confidence=80 >= 70')).toHaveLength(1);
  });
});

function emptyDoc(overrides: Partial<CaptainBriefDocument>): CaptainBriefDocument {
  return {
    version: '1',
    generated_at: '2026-09-19T06:00:00Z',
    summary: '',
    priorities: [],
    recommendations: [],
    health: [],
    operational_intelligence: [],
    engineering: [],
    learning: [],
    opportunities: [],
    warnings: [],
    next_actions: [],
    confidence: null,
    insights: [],
    interrupt_now: [],
    ...overrides,
  };
}

const refs = {
  warnings: { current: null },
  priorities: { current: null },
  next_actions: { current: null },
};

describe('BriefView — Priorities section uses the same fallback order', () => {
  it('shows the description, not the raw scoring trace, for a description-only priority item', () => {
    const doc = emptyDoc({
      priorities: [item({ description: 'Scraped headline: market volatility spikes', recommendation: null })],
    });
    render(<BriefView doc={doc} refs={refs} />);
    expect(screen.getByText('Scraped headline: market volatility spikes')).toBeInTheDocument();
    expect(screen.queryByText(/importance=90/)).not.toBeInTheDocument();
  });
});
