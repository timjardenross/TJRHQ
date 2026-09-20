'use client';

import { useEffect, useState } from 'react';

type AttentionMode = 'urgent' | 'quiet' | 'not-now';
const KEY = 'tjr-attention-mode-v1';

export function AttentionControls({ label = 'Attention mode' }: { label?: string }) {
  const [mode, setMode] = useState<AttentionMode>('urgent');
  useEffect(() => { try { setMode((localStorage.getItem(KEY) as AttentionMode) || 'urgent'); } catch { /* optional preference */ } }, []);
  function choose(next: AttentionMode) { setMode(next); try { localStorage.setItem(KEY, next); } catch { /* optional preference */ } }
  return <div className="flex flex-wrap items-center gap-2 rounded-lg border border-wb-line bg-wb-surface px-3 py-2" aria-label={label}><span className="text-[11px] text-wb-ink2">{label}</span>{([['urgent', 'Urgent first'], ['quiet', 'Quiet queue'], ['not-now', 'Not now']] as const).map(([key, text]) => <button key={key} type="button" aria-pressed={mode === key} onClick={() => choose(key)} className={`rounded-md border px-2.5 py-1.5 text-[11px] ${mode === key ? 'border-wb-sage-deep bg-wb-sage-deep/20 text-wb-ink' : 'border-wb-line text-wb-ink2'}`}>{text}</button>)}</div>;
}
