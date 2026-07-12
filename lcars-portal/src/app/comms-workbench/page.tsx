'use client';

/**
 * Communications Workbench — Phase 1C (health + operational convergence)
 * Direct-URL only (not yet in nav) per COMMS-UI-REDESIGN-SPEC.md rollout plan.
 * Signals -> batch opportunity creation -> Pipeline -> Portfolio + export.
 *
 * Standalone Shell (no LCARS app chrome), matching intelligence-workbench.
 */

import { useState } from 'react';
import { Tabs } from '@/components/ui';
import { Shell } from '../intelligence-workbench/_components/Shell';
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
    <Shell
      title="Communications Workbench"
      eyebrow="Signal-driven content pipeline"
      right={<DomainToggle domain={domain} onChange={setDomain} />}
    >
      <Tabs tabs={TABS} active={tab} onChange={selectTab} ariaLabel="Communications Workbench sections" />

      <div className="mt-4">
        {tab === 'signals' && <SignalsTab domain={domain} />}
        {tab === 'pipeline' && <PipelineTab domain={domain} />}
        {tab === 'portfolio' && <PortfolioTab domain={domain} />}
      </div>

      <div aria-live="polite" aria-atomic="true" className="sr-only">{announce}</div>
    </Shell>
  );
}
