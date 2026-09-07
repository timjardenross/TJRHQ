'use client';

import { Badge, toneToStatus } from '@/components/ui';
import { lifecycleStateToTone, valueToTone } from '@/lib/departments';
import { CHANGE_CLASS_LABEL, type Opportunity } from './types';

export function OpportunityCard({
  opportunity,
  selected,
  onSelect,
}: {
  opportunity: Opportunity;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left p-3 rounded border transition-colors ${
        selected ? 'bg-wb-surface border-wb-sage-deep' : 'bg-wb-bg border-wb-line hover:border-wb-sage-deep'
      }`}
    >
      <div className="font-semibold text-sm text-wb-ink">{opportunity.title}</div>
      {opportunity.summary && (
        <p className="mt-1 text-xs text-wb-ink2 line-clamp-2">{opportunity.summary}</p>
      )}
      <div className="flex gap-2 mt-2 flex-wrap">
        <span className="text-xs bg-wb-line text-wb-ink2 px-2 py-1 rounded">
          {CHANGE_CLASS_LABEL[opportunity.change_class] ?? opportunity.change_class}
        </span>
        {opportunity.value && (
          <Badge status={toneToStatus(valueToTone(opportunity.value))}>{opportunity.value} value</Badge>
        )}
        <Badge status={toneToStatus(lifecycleStateToTone(opportunity.lifecycle_state))}>
          {opportunity.lifecycle_state.replace('_', ' ')}
        </Badge>
        {opportunity.discovery_source === 'external' && (
          <span className="text-xs text-wb-ink2 px-2 py-1">external</span>
        )}
      </div>
    </button>
  );
}
