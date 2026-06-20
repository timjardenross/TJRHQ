'use client';

/**
 * HSF-001 — Human Systems command surface.
 *
 * The Captain-facing dashboard for the Human Systems Framework. Leads with the
 * live capacity panel and frames the two-way operating model (Captain-pulled
 * support + system-pushed intelligence).
 */

import Link from 'next/link';
import { LCARSPanel } from '@/components/LCARSPanel';
import { HumanSystemsPanel } from '@/components/HumanSystemsPanel';

const PULL_REQUESTS = [
  ['/hs today', 'Read today’s capacity and what fits'],
  ['/hs plan low-capacity', 'A protected low-capacity day plan'],
  ['/hs plan recovery', 'A recovery plan for the next few days'],
  ['/hs plan movement', 'A capacity-based, pain-aware movement plan'],
  ['/hs plan nutrition', 'Practical nutrition anchors'],
  ['/hs explain', 'Interpret today’s signal'],
  ['/hs review', 'Weekly Human Systems review']
];

const PUSH_OUTPUTS = [
  ['Morning readiness pulse', 'A concise read of today’s capacity and what fits'],
  ['Evening recovery reflection', 'A gentle end-of-day recovery prompt'],
  ['Capacity degradation alert', 'A leading-indicator warning before capacity is lost'],
  ['Weekly Human Systems review', 'Trends across the six domains']
];

export default function HumanSystemsPage() {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted">
          HSF-001 · Human Operating System
        </p>
        <h1 className="font-lcars text-2xl font-bold text-medical">Human Systems</h1>
        <p className="mt-1 max-w-2xl text-sm text-lcars-text/80 leading-relaxed">
          An operational-resilience layer across movement, nutrition, sleep, mind, performance,
          and resilience. The system reads available data and surfaces evidence-informed,
          non-diagnostic support — you remain the decision-maker.
        </p>
      </header>

      <HumanSystemsPanel />

      <div className="grid gap-4 lg:grid-cols-2">
        <LCARSPanel title="Ask for support" accent="command" eyebrow="Captain-pulled">
          <ul className="flex flex-col gap-2">
            {PULL_REQUESTS.map(([cmd, desc]) => (
              <li key={cmd} className="flex flex-col">
                <code className="text-xs text-medical">{cmd}</code>
                <span className="text-xs text-lcars-text/70">{desc}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[11px] text-lcars-muted">
            Available via Slack Commander (and Telegram XO once enabled).
          </p>
        </LCARSPanel>

        <LCARSPanel title="System-pushed intelligence" accent="science" eyebrow="Proactive">
          <ul className="flex flex-col gap-2">
            {PUSH_OUTPUTS.map(([title, desc]) => (
              <li key={title} className="flex flex-col">
                <span className="text-xs font-semibold text-lcars-text">{title}</span>
                <span className="text-xs text-lcars-text/70">{desc}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[11px] text-lcars-muted">
            Outputs are labelled information · trend · risk signal · action. Red-flag signals
            always escalate to professional support first.
          </p>
        </LCARSPanel>
      </div>

      <p className="text-[11px] text-lcars-muted">
        See also{' '}
        <Link href="/medical" className="text-medical underline">
          Medical Bay
        </Link>{' '}
        and{' '}
        <Link href="/recovery-brief" className="text-medical underline">
          Recovery Brief
        </Link>
        . Doctrine: governance/HUMAN-SYSTEMS-DOCTRINE.md.
      </p>
    </div>
  );
}
