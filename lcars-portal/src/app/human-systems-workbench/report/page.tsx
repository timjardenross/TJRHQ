'use client';

// Human Systems Workbench — Clinician Report.
//
// A fixed 14-day, print-first page built to be downloaded as a PDF and sent
// to an external reader (Captain's psychologist) ahead of a session — see
// api/human-systems/report/summary.ts's header for why this is a separate
// thing from the Trends page's own "What Changed" card (different audience,
// different voice, fixed window instead of a toggle).
//
// The Trends page's "Download PDF" button now points here (2026-09-07)
// instead of window.print()-ing the raw dashboard — a clinician doesn't
// need 11 sparkline tiles, they need "what changed and what's worth
// discussing," in plain language, on one clean page.

import { useEffect, useState } from 'react';
import { WorkbenchShell, Card } from '@/components/ui';

interface SummaryStats {
  totalDays: number;
  recordedDays: number;
  capacityCounts: { green: number; orange: number; red: number };
  capacityRecorded: number;
  capacityTransitions: number;
  painValues: number[];
  drivers: { label: string; coverage: number; concerningCount: number; rate: number }[];
}

interface ReportContent {
  highlights: string[];
  changes: string[];
  focus: string[];
}

interface ReportResponse {
  window_days: number;
  since: string;
  until: string;
  stats: SummaryStats;
  report: ReportContent;
  source: 'llm' | 'fallback';
}

function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
}

function Section({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div>
      <div className="text-[12px] font-semibold uppercase tracking-[0.12em] text-wb-ink">{title}</div>
      {items.length > 0 ? (
        <ul className="mt-2 list-disc space-y-1.5 pl-5 text-[13px] leading-relaxed text-wb-ink">
          {items.map((item, i) => <li key={i}>{item}</li>)}
        </ul>
      ) : (
        <p className="mt-2 text-[13px] italic text-wb-ink2">{empty}</p>
      )}
    </div>
  );
}

export default function HumanSystemsReportPage() {
  const [data, setData] = useState<ReportResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/human-systems/report', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => {
        if (d?.error) throw new Error(d.error);
        setData(d);
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : 'Failed to load report'));
  }, []);

  const stats = data?.stats;

  return (
    <WorkbenchShell
      title="Human Systems — Report"
      eyebrow="14-Day Summary"
      tagline="USS TJR · Built only from what was actually recorded — never a value it doesn't have"
      back={{ href: '/human-systems-workbench/trends', label: 'Trends' }}
    >
      {/* Print-first target: everything but this page's own content is
       *  hidden (Sidebar/header/QuickCapture/MobileCommandBar are global
       *  WorkbenchShell chrome with no print:hidden of their own — none of
       *  the other *-workbench print targets scope this either, but a
       *  document leaving the app for an external reader is the one place
       *  it actually matters). Single-page-friendly tight margins, same
       *  approach as the Trends page's own print stylesheet. */}
      <style>{`
        @media print {
          @page { size: auto; margin: 14mm; }
          header, aside, nav[aria-label="Command MVP"], button[aria-label="Quick capture"] { display: none !important; }
          .print-compact { padding: 0.75rem !important; }
        }
      `}</style>

      <div className="flex flex-col gap-4 print:gap-3">
        <div className="flex items-center justify-between gap-3 print:hidden">
          <p className="text-[13px] text-wb-ink2">
            {data ? `${formatDate(data.since)} – ${formatDate(data.until)}` : loadError ? 'Failed to load' : 'Loading…'}
          </p>
          <button
            onClick={() => window.print()}
            disabled={!data}
            className="rounded-md border border-wb-line px-3 py-1 text-[11px] font-medium text-wb-ink transition hover:border-wb-sage-deep disabled:opacity-50"
          >
            Download PDF
          </button>
        </div>

        {loadError && (
          <div className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-4 text-[13px] text-wb-crit-on">
            Couldn&rsquo;t load the report: {loadError}
          </div>
        )}

        {data && (
          <>
            <div>
              <h1 className="font-serif text-xl text-wb-ink">Human Systems — 14-Day Summary</h1>
              <p className="mt-1 text-[12px] text-wb-ink2">
                {formatDate(data.since)} – {formatDate(data.until)} · prepared for my psychologist ·
                {' '}generated {new Date().toLocaleString('en-AU')}
              </p>
            </div>

            {stats && stats.recordedDays < 2 && (
              <Card className="print-compact">
                <p className="text-[13px] text-wb-ink">
                  Only {stats.recordedDays} of the last {stats.totalDays} days have anything recorded — too little
                  to summarize meaningfully yet.
                </p>
              </Card>
            )}

            <Card className="print-compact flex flex-col gap-5">
              <Section title="Highlights" items={data.report.highlights} empty="Nothing notable to highlight this fortnight." />
              <Section title="Notable Changes" items={data.report.changes} empty="No clear changes from the pattern before this window." />
              <Section title="Focus for This Session" items={data.report.focus} empty="Nothing specific standing out to flag." />
            </Card>

            {stats && stats.recordedDays > 0 && (
              <Card className="print-compact print-tile" style={{ breakInside: 'avoid' }}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-wb-ink2">At a Glance</div>
                <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[13px] text-wb-ink sm:grid-cols-4">
                  <div>
                    <dt className="text-[11px] text-wb-ink2">Days recorded</dt>
                    <dd>{stats.recordedDays} of {stats.totalDays}</dd>
                  </div>
                  {stats.capacityRecorded > 0 && (
                    <div>
                      <dt className="text-[11px] text-wb-ink2">Capacity</dt>
                      <dd>{stats.capacityCounts.green} sustainable · {stats.capacityCounts.orange} stretched · {stats.capacityCounts.red} depleted</dd>
                    </div>
                  )}
                  {stats.painValues.length > 0 && (
                    <div>
                      <dt className="text-[11px] text-wb-ink2">Pain (0-10)</dt>
                      <dd>
                        avg {(stats.painValues.reduce((a, b) => a + b, 0) / stats.painValues.length).toFixed(1)},
                        {' '}max {Math.max(...stats.painValues)} ({stats.painValues.length} day(s))
                      </dd>
                    </div>
                  )}
                  {stats.capacityRecorded > 1 && (
                    <div>
                      <dt className="text-[11px] text-wb-ink2">Capacity changes</dt>
                      <dd>{stats.capacityTransitions} of {stats.capacityRecorded - 1} possible day-to-day shifts</dd>
                    </div>
                  )}
                </dl>
              </Card>
            )}

            <p className="text-[10px] text-wb-ink2 print:mt-2">
              This is a personal tracking summary, not a clinical assessment — generated{' '}
              {data.source === 'llm' ? 'with AI assistance from' : 'directly from'} the numbers above,
              nothing invented beyond what was actually recorded.
            </p>
          </>
        )}
      </div>
    </WorkbenchShell>
  );
}
