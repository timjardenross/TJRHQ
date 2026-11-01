// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';

// The workbench shows four stages (To decide / In progress / Done / Closed).
// HQ's finer internal states survive as a badge inside a stage. The page must
// work against BOTH backend vocabularies (old: fine lifecycle_state; new:
// stage in lifecycle_state + fine value in stage_detail) so the portal and the
// engine can deploy in either order.

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: () => {}, replace: () => {} }),
  usePathname: () => '/self-improvement-findings',
}));

import HqEvolutionPage from '../page';

function opp(id: string, title: string, lifecycle_state: string, extra: Record<string, unknown> = {}) {
  return {
    opportunity_id: id, title, change_class: 'capability', discovery_source: 'external',
    lifecycle_state, fingerprint: id, summary: '', why_relevant: '', investigation: {}, provenance: [],
    missing_evidence: [], outcome: {}, outcome_contract: {}, confidence: 0.5, evidence_strength: 'moderate',
    created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-02T00:00:00Z', ...extra,
  };
}

// One of each fine state, in the OLD vocabulary.
const OLD_VOCAB = [
  opp('EVO-1', 'Researching one', 'discovered'),
  opp('EVO-2', 'Researching two', 'investigating'),
  opp('EVO-3', 'Needs decision', 'proposed'),
  opp('EVO-4', 'Approved one', 'approved'),
  opp('EVO-5', 'Being built', 'implementing'),
  opp('EVO-6', 'Being checked', 'verifying'),
  opp('EVO-7', 'Finished one', 'learned'),
  opp('EVO-8', 'Parked one', 'watching', { watch_reason: 'premature' }),
  opp('EVO-9', 'Rejected one', 'rejected', { rejection_reason: 'no fit' }),
  opp('EVO-10', 'Already fixed', 'resolved_before_research'),
];

// The same data in the NEW vocabulary.
const STAGE_OF: Record<string, string> = {
  discovered: 'researching', investigating: 'researching', proposed: 'to_decide', approved: 'in_progress',
  implementing: 'in_progress', verifying: 'in_progress', learned: 'done', watching: 'closed',
  rejected: 'closed', resolved_before_research: 'closed',
};
const NEW_VOCAB = OLD_VOCAB.map((o) => ({ ...o, lifecycle_state: STAGE_OF[o.lifecycle_state], stage_detail: o.lifecycle_state }));

function mockApi(opportunities: unknown[]) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const body = url.includes('/opportunities') ? { opportunities }
      : url.includes('/evolution-summary') ? { has_run_yet: false }
      : url.includes('/findings') ? { findings: [] }
      : url.includes('/mission-dispatch-status') ? { dispatches: {} }
      : {};
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// Tabs renders a <nav aria-label="Improvements sections"> of buttons (not role=tab).
// Scoped to that nav so the same-named stage tiles above it are not matched.
const tabNav = () => within(screen.getByRole('navigation', { name: 'Improvements sections' }));
const tabButton = (name: RegExp) => tabNav().getByRole('button', { name });

describe.each([
  ['old vocabulary', OLD_VOCAB],
  ['new vocabulary', NEW_VOCAB],
])('Improvements workbench (%s)', (_name, data) => {
  it('shows exactly four stages with counts, and hides items HQ is still researching', async () => {
    mockApi(data);
    render(<HqEvolutionPage />);
    const strip = await screen.findByRole('list', { name: 'Improvements stages' });
    const tiles = within(strip).getAllByRole('listitem');
    expect(tiles).toHaveLength(4);
    // to decide 1, in progress 3, done 1, closed 3 — the 2 researching items are not counted
    const counts = tiles.map((t) => within(t).getByText(/^\d+$/).textContent);
    expect(counts).toEqual(['1', '3', '1', '3']);
    expect(screen.queryByText('Researching one')).not.toBeInTheDocument();
    expect(screen.queryByText('Researching two')).not.toBeInTheDocument();
    expect(screen.getByText(/still researching 2 other candidates/i)).toBeInTheDocument();
  });

  it('offers only the four stage tabs (no Discover / Investigate / Improve / Learned / Rejected)', async () => {
    mockApi(data);
    render(<HqEvolutionPage />);
    await screen.findByRole('list', { name: 'Improvements stages' });
    const tabs = tabNav().getAllByRole('button').map((t) => t.textContent ?? '');
    expect(tabs).toHaveLength(4);
    expect(tabs[0]).toMatch(/^To decide/);
    expect(tabs[1]).toMatch(/^In progress/);
    expect(tabs[2]).toMatch(/^Done/);
    expect(tabs[3]).toMatch(/^Closed/);
  });

  it('To decide lists the proposed item; In progress lists approved, implementing and verifying', async () => {
    const user = userEvent.setup();
    mockApi(data);
    render(<HqEvolutionPage />);
    expect(await screen.findByText('Needs decision')).toBeInTheDocument();

    await user.click(tabButton(/^In progress/));
    for (const t of ['Approved one', 'Being built', 'Being checked']) expect(screen.getByText(t)).toBeInTheDocument();
    expect(screen.queryByText('Needs decision')).not.toBeInTheDocument();
  });

  it('Closed groups rejected, parked and already-resolved, with a reason on each and a way back for parked items', async () => {
    const user = userEvent.setup();
    mockApi(data);
    render(<HqEvolutionPage />);
    await screen.findByText('Needs decision');

    await user.click(tabButton(/^Closed/));
    for (const t of ['Parked one', 'Rejected one', 'Already fixed']) expect(screen.getByText(t)).toBeInTheDocument();
    expect(screen.getByText('Parked — revisit later')).toBeInTheDocument();
    expect(screen.getByText('Rejected')).toBeInTheDocument();
    expect(screen.getByText(/Already resolved/)).toBeInTheDocument();

    await user.click(screen.getByText('Parked one'));
    expect(await screen.findByRole('button', { name: 'Move back to To decide' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reject for good' })).toBeInTheDocument();

    // a plain rejected item has no such actions
    await user.click(screen.getByText('Rejected one'));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Move back to To decide' })).not.toBeInTheDocument());
  });

  it('Done lists the learned item', async () => {
    const user = userEvent.setup();
    mockApi(data);
    render(<HqEvolutionPage />);
    await screen.findByText('Needs decision');
    await user.click(tabButton(/^Done/));
    expect(screen.getByText('Finished one')).toBeInTheDocument();
  });
});
