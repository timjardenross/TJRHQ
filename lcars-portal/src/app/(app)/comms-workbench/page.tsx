'use client';

/**
 * Communications Workbench — Phase 1C (health + operational convergence)
 * Direct-URL only (not yet in nav) per COMMS-UI-REDESIGN-SPEC.md rollout plan.
 * Signals -> batch opportunity creation -> Pipeline -> Portfolio + export.
 */

import { useState } from 'react';
import { DomainToggle } from './_components/DomainToggle';
import { SignalsTab } from './_components/SignalsTab';
import { PipelineTab } from './_components/PipelineTab';
import { PortfolioTab } from './_components/PortfolioTab';
import type { Domain } from './_components/shared';

type Tab = 'signals' | 'pipeline' | 'portfolio';

const TABS: { key: Tab; label: string }[] = [
  { key: 'signals', label: 'Signals' },
  { key: 'pipeline', label: 'Pipeline' },
  { key: 'portfolio', label: 'Portfolio' },
];

export default function CommsWorkbenchPage() {
  const [tab, setTab] = useState<Tab>('signals');
  const [domain, setDomain] = useState<Domain>('both');
  const [announce, setAnnounce] = useState('');

  function selectTab(t: Tab) {
    setTab(t);
    setAnnounce(`Switched to ${TABS.find(x => x.key === t)?.label} tab`);
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold uppercase tracking-wider text-[#18223a]">
            Communications Workbench
          </h1>
          <p className="text-sm text-[#61718c]">
            Signal-driven content pipeline — health + operational intelligence, one flow.
          </p>
        </div>
        <DomainToggle domain={domain} onChange={setDomain} />
      </header>

      <nav className="flex gap-2 border-b border-[#d9e1f0] pb-2" aria-label="Communications Workbench sections">
        {TABS.map(t => (
          <button
            key={t.key}
            type="button"
            onClick={() => selectTab(t.key)}
            aria-current={tab === t.key ? 'page' : undefined}
            className={`text-xs px-3 py-1.5 rounded border transition-colors ${
              tab === t.key
                ? 'border-[#243b7a] text-[#243b7a] bg-[#243b7a]/10'
                : 'border-[#d9e1f0] text-[#61718c] hover:text-[#18223a]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <div>
        {tab === 'signals' && <SignalsTab domain={domain} />}
        {tab === 'pipeline' && <PipelineTab domain={domain} />}
        {tab === 'portfolio' && <PortfolioTab domain={domain} />}
      </div>

      <div aria-live="polite" aria-atomic="true" className="sr-only">{announce}</div>
    </div>
  );
}
