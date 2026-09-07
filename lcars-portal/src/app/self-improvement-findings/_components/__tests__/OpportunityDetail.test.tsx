// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

import { OpportunityDetail } from '../OpportunityDetail';
import type { Opportunity } from '../types';

afterEach(cleanup);

// 2026-09-07: HandoffPRStrategy (scripts/self_improvement/auto_remediation.py)
// and mission_dispatch.py both report success=true even when NO PR was
// actually opened — an existing-file edit deferred to manual review, or
// no_files_written both still return success=true with an explanatory
// message and no pr_url. remediation_status alone was being used as a
// proxy for "a PR exists", which is wrong and — confirmed live on real
// opportunities — falsely told the Captain a PR was waiting to merge when
// none existed. Must gate on the real remediation_pr_url instead.

function baseOpportunity(overrides: Partial<Opportunity> = {}): Opportunity {
  return {
    opportunity_id: 'EVO-TEST',
    title: 'Test opportunity',
    change_class: 'reliability',
    discovery_source: 'internal',
    lifecycle_state: 'approved',
    fingerprint: 'fp-test',
    summary: 'A test opportunity',
    why_relevant: 'because tests',
    value: 'medium',
    cost_impact: 'neutral',
    complexity: 'low',
    fit: 'moderate',
    risk_level: 'medium',
    relevance_score: 0.5,
    confidence: 0.9,
    evidence_strength: 'conclusive',
    investigation: {},
    provenance: [],
    watch_reason: null,
    rejection_reason: null,
    missing_evidence: [],
    outcome: {},
    outcome_contract: {},
    validation_result: null,
    validation_evidence: [],
    validated_at: null,
    source_finding_id: 'FND-TEST',
    mission_id: null,
    automation_eligibility: 'needs_signoff',
    policy_decision_rationale: null,
    created_at: '2026-09-06T00:00:00Z',
    updated_at: '2026-09-06T00:00:00Z',
    run_id: null,
    ...overrides,
  };
}

describe('OpportunityDetail — Auto-remediation section', () => {
  it('shows the real message, not a false "Draft PR opened", when succeeded but no PR was opened', () => {
    const opportunity = baseOpportunity({
      remediation_status: 'succeeded',
      remediation_pr_url: null,
      remediation_message: 'Handoff coded (artifact: x.patch.md) but no PR opened (no_files_written) — review the artifact manually.',
    });
    render(<OpportunityDetail opportunity={opportunity} />);
    expect(screen.getByText(/no PR opened/i)).toBeInTheDocument();
    expect(screen.queryByText(/Draft PR opened for review/i)).not.toBeInTheDocument();
  });

  it('shows the real PR link when one genuinely exists', () => {
    const opportunity = baseOpportunity({
      remediation_status: 'succeeded',
      remediation_pr_url: 'https://github.com/timjardenross/TJRHQ/pull/56',
      remediation_message: 'Draft PR opened for review: https://github.com/timjardenross/TJRHQ/pull/56',
    });
    render(<OpportunityDetail opportunity={opportunity} />);
    expect(screen.getByText(/Draft PR opened for review/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /pull\/56/ })).toHaveAttribute(
      'href',
      'https://github.com/timjardenross/TJRHQ/pull/56'
    );
  });

  it('renders nothing in the Auto-remediation section when remediation_status is absent', () => {
    const opportunity = baseOpportunity();
    render(<OpportunityDetail opportunity={opportunity} />);
    expect(screen.queryByText(/Auto-remediation/i)).not.toBeInTheDocument();
  });
});
