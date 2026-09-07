'use client';

/**
 * SourcesTabView — nested "Sources" tab composer (HQ Status IA uplift).
 *
 * The old top-level nav had two separate tabs, "Source Health" and
 * "Pipeline Health", each owning its own data-fetching component
 * (SourcesView / PipelineHealthView). The new simplified nav collapses
 * both into a single "Sources" tab; this component recomposes them
 * behind a small secondary in-tab toggle rather than merging or
 * duplicating either view's logic.
 *
 * Reuses DomainToggle (the canonical workbench tab switch — see
 * src/components/ui/DomainToggle.tsx) for the nested toggle so this gets
 * the same accessible tablist keyboard behaviour as the primary nav, just
 * scoped down visually since it's a secondary control, not the page's
 * main navigation.
 */
import { useState } from 'react';
import { DomainToggle } from '@/components/ui';
import { SourcesView } from './SourcesView';
import { PipelineHealthView } from './PipelineHealthView';

type SourcesSubTab = 'source-health' | 'pipeline-health';

const SUB_TAB_OPTIONS: { key: SourcesSubTab; label: string }[] = [
  { key: 'source-health', label: 'Source Health' },
  { key: 'pipeline-health', label: 'Pipeline Health' },
];

export function SourcesTabView() {
  const [subTab, setSubTab] = useState<SourcesSubTab>('source-health');

  return (
    <div>
      {/* Secondary, in-tab toggle — deliberately smaller/quieter than the
          primary DomainToggle in page.tsx's tab bar so it reads as a
          nested control, not another top-level nav. */}
      <div className="mb-3 flex text-[12px] [&_[role=tablist]]:py-0.5 [&_[role=tab]]:px-2 [&_[role=tab]]:py-1 [&_[role=tab]]:text-[12px]">
        <DomainToggle
          value={subTab}
          onChange={setSubTab}
          options={SUB_TAB_OPTIONS}
          ariaLabel="Sources sections"
        />
      </div>
      {subTab === 'source-health' && <SourcesView />}
      {subTab === 'pipeline-health' && <PipelineHealthView />}
    </div>
  );
}
