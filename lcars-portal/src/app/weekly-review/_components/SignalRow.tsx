'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui';
import { createTask } from '@/lib/personalTasks';
import type { Signal } from '@/lib/weeklyReview';

const DOT_CLASS: Record<Signal['tone'], string> = {
  ok: 'bg-wb-ok',
  warn: 'bg-wb-warn',
  crit: 'bg-wb-crit',
  neutral: 'bg-wb-ink2',
};

// Weekly Review's own tone already reflects how pressing a finding is —
// reuse it as urgency/importance instead of dropping that signal on the
// floor when the item becomes a Ready Room task.
const TONE_URGENCY: Record<Signal['tone'], number> = { crit: 5, warn: 4, ok: 2, neutral: 3 };

// Exported 2026-09-05 (Weekly Review synthesis mission) so CarryForward.tsx
// can reuse the exact same "→ Ready Room" createTask() action for signal
// items it surfaces, instead of a second action implementation.
export function ItemRow({
  id, title, href, meta, sourceLabel, signalLabel, tone,
}: {
  id: string; title: string; href?: string; meta?: string;
  sourceLabel: string; signalLabel: string; tone: Signal['tone'];
}) {
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function sendToReadyRoom() {
    setBusy(true);
    // Carry the finding's full context across, not just the bare title —
    // which workbench/signal it came from, its meta, and a link back to it.
    const contextParts = [`From ${sourceLabel} · ${signalLabel}.`];
    if (meta) contextParts.push(meta);
    if (href) contextParts.push(href);
    await createTask({
      title,
      category: 'follow_up',
      context: contextParts.join(' '),
      urgency: TONE_URGENCY[tone],
      importance: TONE_URGENCY[tone],
    });
    setBusy(false);
    setSent(true);
  }

  return (
    <li className="flex items-center justify-between gap-2 py-1 text-[12px]">
      <span className="min-w-0 truncate text-wb-ink">
        {href ? <Link href={href} className="hover:underline">{title}</Link> : title}
        {meta && <span className="ml-1.5 text-wb-ink2">· {meta}</span>}
      </span>
      {sent ? (
        <span className="shrink-0 text-[11px] text-wb-ok-on">Sent ✓</span>
      ) : (
        <button
          type="button"
          disabled={busy}
          onClick={sendToReadyRoom}
          className="shrink-0 text-[11px] text-wb-sage-deep hover:underline disabled:opacity-40"
        >
          → Ready Room
        </button>
      )}
      <span className="sr-only">{id}</span>
    </li>
  );
}

/** One review signal — a count with a tone dot, expandable to its item list.
 * "Unavailable" (query failed) reads honestly as "couldn't check", never as
 * a false zero. */
export function SignalRow({ signal, sourceLabel }: { signal: Signal; sourceLabel: string }) {
  const [expanded, setExpanded] = useState(false);
  const hasItems = signal.items.length > 0;

  return (
    <div>
      <button
        type="button"
        onClick={() => hasItems && setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 py-1 text-left text-[13px] disabled:cursor-default"
        disabled={!hasItems}
      >
        <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${DOT_CLASS[signal.tone]}`} />
        <span className="flex-1 text-wb-ink">{signal.label}</span>
        <span className="shrink-0 text-wb-ink2">
          {signal.unavailable ? 'unavailable' : signal.count}
        </span>
        {hasItems && <span className="shrink-0 text-[10px] text-wb-ink2">{expanded ? '▲' : '▼'}</span>}
      </button>
      {expanded && hasItems && (
        <ul className="ml-4 border-l border-wb-line pl-3">
          {signal.items.map((it) => (
            <ItemRow key={it.id} {...it} sourceLabel={sourceLabel} signalLabel={signal.label} tone={signal.tone} />
          ))}
        </ul>
      )}
    </div>
  );
}
