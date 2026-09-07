'use client';

// Proactive advisory (mission §17) — simplified from a raw trigger dump to
// "Something worth considering". Still POST /api/advisory {action:proactive}
// (core/advisory/proactive.py — confidence/outcome decline, escalation risk,
// repeated blockers, capacity overload, health deterioration, opportunities)
// and still NOTICES, DOES NOT ACT: no task/Mission is created, no action is
// dispatched. "Think it through" only prefills Think's input — the user
// still has to ask.

import { useEffect, useState } from 'react';
import type { AdvisoryResult } from './types';

export function ProactiveBanner({ onThinkItThrough }: { onThinkItThrough: (text: string) => void }) {
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
  // triggers are Trigger dataclass dicts {trigger_type, level, message, source}
  const rawTriggers = (signals.triggers ?? []) as Array<string | { message?: string; trigger_type?: string }>;
  const triggerList = rawTriggers.map((t) =>
    typeof t === 'string' ? t : (t.message ?? t.trigger_type ?? String(t))
  );
  const observation = signals.headline || triggerList[0] || 'Something in your advisory history may be worth a closer look.';

  return (
    <div className={`flex items-start gap-3 rounded-md border px-3 py-2.5 text-sm ${isUrgent ? 'border-wb-warn/50 bg-wb-warn/10' : 'border-wb-sage-deep/30 bg-wb-sage-deep/5'}`}>
      <span aria-hidden="true" className={`mt-0.5 shrink-0 text-xs font-bold ${isUrgent ? 'text-wb-warn-on' : 'text-wb-sage-deep'}`}>
        {isUrgent ? '▲' : '●'}
      </span>
      <div className="min-w-0 flex-1">
        <p className={`text-[10px] font-semibold uppercase tracking-[0.15em] ${isUrgent ? 'text-wb-warn-on' : 'text-wb-sage-deep'}`}>Something worth considering</p>
        <p className="mt-0.5 text-[13px] text-wb-ink">{observation}</p>
        {triggerList.length > 1 && (
          <p className="mt-0.5 text-[11px] text-wb-ink2">{triggerList.slice(1, 3).join(' · ')}{triggerList.length > 3 ? ` +${triggerList.length - 3} more` : ''}</p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <button onClick={() => { onThinkItThrough(observation); setDismissed(true); }}
          className="text-[10px] font-semibold uppercase tracking-widest text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
          Think it through
        </button>
        <button onClick={() => setDismissed(true)}
          className="text-[10px] uppercase tracking-widest text-wb-ink2 transition-colors hover:text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
          Not useful
        </button>
      </div>
    </div>
  );
}
