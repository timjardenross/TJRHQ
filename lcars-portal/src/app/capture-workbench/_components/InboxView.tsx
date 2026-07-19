'use client';

// Phase C — Capture Inbox (triage). Ported from the legacy Capture page
// CaptureInbox. Reuses fetchInboxCaptures() unchanged. Reloads on the page's
// live signal (refreshSignal, driven by the captured_items realtime channel)
// and after any row action; bumps KPI stats via onMutated.

import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/ui';
import { fetchInboxCaptures, type InboxCapture, type CaptureClassification } from '@/lib/capture';
import { CaptureRow } from './CaptureRow';
import { INBOX_FILTERS, type InboxFilter } from './types';

function filterToQuery(f: InboxFilter): {
  source?: string;
  classification?: CaptureClassification;
  statusFilter?: 'pending' | 'routed';
} {
  if (f === 'routed')         return { statusFilter: 'routed' };
  if (f === 'portal')         return { source: 'lcars-mobile-quick-capture' };
  if (f === 'telegram-voice') return { source: 'telegram-xo-voice-capture' };
  if (f === 'mission')        return { classification: 'mission' };
  if (f === 'health')         return { classification: 'personal' };
  if (f === 'research')       return { classification: 'research' };
  if (f === 'decision')       return { classification: 'decision' };
  if (f === 'unclassified')   return { classification: 'unclassified' };
  return {};
}

export function InboxView({
  activeFilter,
  onFilterChange,
  refreshSignal,
  onMutated,
}: {
  activeFilter: InboxFilter;
  onFilterChange: (f: InboxFilter) => void;
  refreshSignal: number;
  onMutated: () => void;
}) {
  const [items, setItems] = useState<InboxCapture[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (filter: InboxFilter) => {
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchInboxCaptures({ ...filterToQuery(filter), limit: 100 });
      setItems(rows);
    } catch {
      setError('Could not load inbox.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(activeFilter); }, [activeFilter, refreshSignal, load]);

  const handleRefresh = useCallback(() => { load(activeFilter); onMutated(); }, [activeFilter, load, onMutated]);

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2">Capture Inbox</p>
        {!loading && <span className="text-[10px] text-wb-ink2">{items.length} item{items.length !== 1 ? 's' : ''}</span>}
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {INBOX_FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => onFilterChange(f.key)}
            className={`rounded-md border px-3 py-1 text-xs font-medium transition-colors ${
              activeFilter === f.key ? 'border-wb-sage-deep bg-wb-sage-deep/10 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading && <p className="py-4 text-center text-xs uppercase tracking-[0.2em] text-wb-ink2">Loading…</p>}
      {error && !loading && (
        <p className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3 text-sm text-wb-crit-on">{error}</p>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="rounded-md border border-wb-line bg-wb-bg px-4 py-8 text-center">
          <p className="text-sm text-wb-ink2">{activeFilter === 'routed' ? 'No routed captures' : 'No pending captures'}</p>
          <p className="mt-1 text-[11px] text-wb-ink2">
            {activeFilter === 'all'
              ? 'All clear. Use the Capture tab or Telegram to add one.'
              : activeFilter === 'routed'
              ? 'Items appear here after you route or review them.'
              : `No ${activeFilter} captures pending.`}
          </p>
        </div>
      )}
      {!loading && !error && items.length > 0 && (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <CaptureRow key={item.id} item={item} onRefresh={handleRefresh} />
          ))}
        </ul>
      )}
    </Card>
  );
}
