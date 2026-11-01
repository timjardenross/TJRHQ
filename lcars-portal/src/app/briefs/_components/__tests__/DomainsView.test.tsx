// @vitest-environment jsdom
//
// Briefs/Captain's Brief consolidation Phase 3 — DomainsView tests.
//
// The Domains tab needs a real Supabase-authenticated session and a live
// context_service.py to exercise end-to-end in a browser (both api/briefs/
// domains/route.ts and the underlying Python assembly are covered
// separately — see tests/test_domains_view.py for the assembly logic).
// This file verifies the presentation layer directly against hand-built
// DomainsDocument fixtures, covering the three scenarios the mission asks
// for: a normal domain, a domain with no data, and a domain with degraded/
// stale coverage — without needing a live backend or session.

import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { DomainsView } from '../DomainsView';
import type { DomainsDocument, DomainSummary } from '@/lib/domainsShared';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function domain(overrides: Partial<DomainSummary>): DomainSummary {
  return {
    key: 'engineering',
    label: 'Engineering',
    source: 'event_bus',
    posture: 'GREEN',
    confidence: null,
    what_changed: null,
    what_matters: [],
    watch_conditions: [],
    constraints: [],
    evidence_count: 0,
    evidence: [],
    as_of: '2026-09-19T06:00:00Z',
    availability: 'ok',
    detail_href: null,
    ...overrides,
  };
}

describe('DomainsView — loading/error/empty states', () => {
  it('shows a loading message while the first fetch is in flight', () => {
    render(<DomainsView doc={null} loading={true} error={null} />);
    expect(screen.getByText(/Assembling cross-domain picture/)).toBeInTheDocument();
  });

  it('shows the error message when the fetch failed', () => {
    render(<DomainsView doc={null} loading={false} error="Failed to reach the Domains assembly service" />);
    expect(screen.getByText('Failed to reach the Domains assembly service')).toBeInTheDocument();
  });
});

describe('DomainsView — normal domain', () => {
  it('renders posture, confidence, what matters, watch conditions and a drill-down link', () => {
    const doc: DomainsDocument = {
      generated_at: '2026-09-19T06:00:00Z',
      event_bus_as_of: '2026-09-19T06:00:00Z',
      osint_as_of: null,
      osint_available: false,
      warnings: [],
      domains: [
        domain({
          key: 'engineering',
          label: 'Engineering',
          posture: 'AMBER',
          confidence: 82,
          what_changed: '1 item(s) need attention now',
          what_matters: ['Deploy failed on staging'],
          watch_conditions: ['CI queue backing up'],
          evidence_count: 2,
          evidence: [{ title: 'engineering.deploy.failed', detail: 'Deploy failed on staging', risk: 'AMBER' }],
          detail_href: '/briefs/domains/engineering',
        }),
      ],
    };

    render(<DomainsView doc={doc} loading={false} error={null} />);

    expect(screen.getByText('Engineering')).toBeInTheDocument();
    expect(screen.getByText('AMBER')).toBeInTheDocument();
    expect(screen.getByText('Confidence: 82%')).toBeInTheDocument();
    expect(screen.getByText('1 item(s) need attention now')).toBeInTheDocument();
    expect(screen.getByText('Deploy failed on staging')).toBeInTheDocument();
    expect(screen.getByText('CI queue backing up')).toBeInTheDocument();
    expect(screen.getByText('Evidence (2)')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /View full detail/ })).toHaveAttribute('href', '/briefs/domains/engineering');
  });
});

describe('DomainsView — a domain with no data', () => {
  it('still shows the card (does not disappear) with an explicit empty message', () => {
    const doc: DomainsDocument = {
      generated_at: '2026-09-19T06:00:00Z',
      event_bus_as_of: '2026-09-19T06:00:00Z',
      osint_as_of: null,
      osint_available: false,
      warnings: [],
      domains: [
        domain({ key: 'opportunities', label: 'Opportunities', posture: 'UNKNOWN', availability: 'no_data', evidence_count: 0 }),
      ],
    };

    render(<DomainsView doc={doc} loading={false} error={null} />);

    expect(screen.getByText('Opportunities')).toBeInTheDocument();
    expect(screen.getByText('No signals right now')).toBeInTheDocument();
    expect(screen.getByText('No signals in this domain right now.')).toBeInTheDocument();
    // No evidence collapsible for an empty domain.
    expect(screen.queryByText(/Evidence \(/)).not.toBeInTheDocument();
  });
});

describe('DomainsView — degraded / stale coverage', () => {
  it('surfaces the degraded badge on the card and the top-level warning banner', () => {
    // relativeTime() (DomainsView.tsx) computes against the real wall clock
    // (Date.now()), not against `generated_at` — this test's "2d ago"
    // assertion only ever held on whatever real-world day happened to put
    // it exactly 2 days after the fixture's osint_as_of. Pin the clock so
    // the test is deterministic regardless of when it actually runs.
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-19T06:00:00Z'));

    const doc: DomainsDocument = {
      generated_at: '2026-09-19T06:00:00Z',
      event_bus_as_of: '2026-09-19T06:00:00Z',
      osint_as_of: '2026-09-17T06:00:00Z',
      osint_available: true,
      warnings: ["The latest brief's collection cycle was degraded — OSINT domain coverage may be incomplete."],
      domains: [
        domain({
          key: 'technical',
          label: 'Technical',
          source: 'osint',
          posture: 'AMBER',
          availability: 'degraded',
          as_of: '2026-09-17T06:00:00Z',
          evidence_count: 1,
          evidence: [{ title: 'Cyber incident under investigation', detail: null, risk: 'AMBER' }],
          detail_href: '/briefs/brief-123',
        }),
      ],
    };

    render(<DomainsView doc={doc} loading={false} error={null} />);

    expect(screen.getByText('Degraded coverage')).toBeInTheDocument();
    expect(screen.getByText(/collection cycle was degraded/)).toBeInTheDocument();
    expect(screen.getByText(/2d ago/)).toBeInTheDocument();
  });

  it('warns and marks OSINT unavailable when no brief has been generated yet', () => {
    const doc: DomainsDocument = {
      generated_at: '2026-09-19T06:00:00Z',
      event_bus_as_of: '2026-09-19T06:00:00Z',
      osint_as_of: null,
      osint_available: false,
      warnings: ['No OSINT brief has been generated yet — Technical/Regulatory/Environmental/Payments/Health/Emergency domains are unavailable.'],
      domains: [domain({ key: 'health', label: 'Health' })],
    };

    render(<DomainsView doc={doc} loading={false} error={null} />);
    expect(screen.getByText(/No OSINT brief has been generated yet/)).toBeInTheDocument();
  });
});

describe('DomainsView — coverage notes (signal-leakage fix)', () => {
  it('renders constraints under their own "Coverage Notes" heading, separate from What Matters', () => {
    const doc: DomainsDocument = {
      generated_at: '2026-09-19T06:00:00Z',
      event_bus_as_of: '2026-09-19T06:00:00Z',
      osint_as_of: null,
      osint_available: false,
      warnings: [],
      domains: [
        domain({
          key: 'operational_intelligence',
          label: 'Operational Intelligence',
          what_matters: ['A genuine synthesized finding'],
          constraints: [
            '109 intelligence.source.failed event(s) aggregated as a count/trend this cycle — ' +
              'a coverage signal, not an individual finding; see Evidence for the raw events.',
          ],
        }),
      ],
    };

    render(<DomainsView doc={doc} loading={false} error={null} />);

    expect(screen.getByText('Coverage Notes')).toBeInTheDocument();
    expect(screen.getByText(/109 intelligence\.source\.failed event\(s\) aggregated/)).toBeInTheDocument();
    expect(screen.getByText('A genuine synthesized finding')).toBeInTheDocument();
    // Not present when there is nothing to caveat.
    expect(screen.queryAllByText('Coverage Notes')).toHaveLength(1);
  });

  it('omits the Coverage Notes section entirely when there are no constraints', () => {
    const doc: DomainsDocument = {
      generated_at: '2026-09-19T06:00:00Z',
      event_bus_as_of: '2026-09-19T06:00:00Z',
      osint_as_of: null,
      osint_available: false,
      warnings: [],
      domains: [domain({ key: 'engineering', label: 'Engineering' })],
    };

    render(<DomainsView doc={doc} loading={false} error={null} />);
    expect(screen.queryByText('Coverage Notes')).not.toBeInTheDocument();
  });
});

describe('DomainsView — grouping', () => {
  it('groups OSINT and Platform domains under separate headings', () => {
    const doc: DomainsDocument = {
      generated_at: '2026-09-19T06:00:00Z',
      event_bus_as_of: '2026-09-19T06:00:00Z',
      osint_as_of: '2026-09-19T06:00:00Z',
      osint_available: true,
      warnings: [],
      domains: [
        domain({ key: 'engineering', label: 'Engineering', source: 'event_bus' }),
        domain({ key: 'technical', label: 'Technical', source: 'osint', detail_href: '/briefs/brief-1' }),
      ],
    };

    render(<DomainsView doc={doc} loading={false} error={null} />);
    expect(screen.getByText('Platform Domains')).toBeInTheDocument();
    expect(screen.getByText('OSINT / World Intelligence')).toBeInTheDocument();
  });
});
