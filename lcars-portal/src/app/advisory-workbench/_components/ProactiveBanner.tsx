'use client';

// Ported from the legacy Advisory Council ProactiveSignalsBanner (MSN-0206).
// Best-effort: POST /api/advisory {action:proactive}; shows nothing unless
// there are triggers or attention_required. Skin only.

import { useEffect, useState } from 'react';
import type { AdvisoryResult } from './types';

export function ProactiveBanner() {
  const [signals, setSignals] = useState<{ headline?: string; triggers?: unknown[]; attention_required?: boolean } | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    fetch('/api/advisory', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'proactive' }),
    })
      .then((r) => r.json())
      .then((data: { result?: AdvisoryResult }) => {
        const r = data.result ?? (data as unknown as AdvisoryResult);
        const triggers = (r?.triggers ?? []) as unknown[];
        if (triggers.length > 0 || r?.attention_required) setSignals(r as typeof signals);
      })
      .catch(() => { /* proactive signals are best-effort */ });
  }, []);

  if (!signals || dismissed) return null;

  const isUrgent = signals.attention_required;
  const triggerList = (signals.triggers ?? []) as string[];

  return (
    <div className={`flex items-start gap-3 rounded-md border px-3 py-2.5 text-sm ${isUrgent ? 'border-wb-warn/50 bg-wb-warn/10' : 'border-wb-sage-deep/30 bg-wb-sage-deep/5'}`}>
      <span aria-hidden="true" className={`mt-0.5 shrink-0 text-xs font-bold ${isUrgent ? 'text-wb-warn-on' : 'text-wb-sage-deep'}`}>
        {isUrgent ? '▲' : '●'}
      </span>
      <div className="min-w-0 flex-1">
        {signals.headline && (
          <p className={`text-xs font-semibold ${isUrgent ? 'text-wb-warn-on' : 'text-wb-sage-deep'}`}>{signals.headline}</p>
        )}
        {triggerList.length > 0 && (
          <p className="mt-0.5 text-[11px] text-wb-ink2">{triggerList.slice(0, 2).join(' · ')}{triggerList.length > 2 ? ` +${triggerList.length - 2} more` : ''}</p>
        )}
      </div>
      <button onClick={() => setDismissed(true)}
        className="shrink-0 text-[10px] uppercase tracking-widest text-wb-ink2 transition-colors hover:text-wb-ink">
        Dismiss
      </button>
    </div>
  );
}
