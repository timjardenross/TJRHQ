'use client';

// Generic live-data primitive for the new OS. Real-time here means "the
// browser learns a row changed" - it does NOT mean the source that produced
// the row got any faster. Ingestion cadence (e.g. the ORI GitHub brief sync,
// currently a daily cron - see .github/workflows/ori-daily-sync.yml) is a
// separate problem from UI staleness and is fixed separately, per source,
// depending on whether that source can actually push to us.
//
// This hook only solves UI staleness: subscribe to Postgres changes on a
// table via Supabase Realtime and re-run a refetch the moment a row lands,
// however it got there (cron, a future webhook, or a manual insert). Pages
// keep their existing fetch-from-API-route logic as the single source of
// truth for querying/joining/ordering - this hook only decides *when* to
// call it again, never what the data looks like.
//
// Requires the target table to be added to the `supabase_realtime`
// publication (see core/infrastructure/supabase/migrations) and to have a
// SELECT policy covering the subscribing role - Realtime is RLS-gated like
// any other read.

import { useEffect, useRef } from 'react';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

export type RealtimeEvent = 'INSERT' | 'UPDATE' | 'DELETE';

export interface UseRealtimeRefreshOptions {
  /** Table to watch, e.g. "intelligence_events". */
  table: string;
  /** Which change types trigger a refresh. Defaults to inserts only - the
   * common case for "a new item appeared". */
  events?: RealtimeEvent[];
  /** Optional Postgres filter string, e.g. "domain=eq.operational". */
  filter?: string;
  /** Called whenever a matching change arrives. Should trigger the page's
   * normal refetch - this hook never fetches or shapes data itself. */
  onChange: () => void;
  /** Set false to skip subscribing (e.g. while a domain tab isn't active). */
  enabled?: boolean;
  /** Reports the channel's connection state, so UI can show an honest "Live"
   * indicator instead of a hardcoded label - Supabase reports 'SUBSCRIBED'
   * only once the websocket is actually connected. */
  onStatusChange?: (status: 'SUBSCRIBED' | 'CLOSED' | 'CHANNEL_ERROR' | 'TIMED_OUT') => void;
}

/** Subscribes to Postgres changes on `table` for as long as the calling
 * component is mounted and `enabled`. Cleans up its channel on unmount or
 * when the watched table/filter changes. */
export function useRealtimeRefresh({
  table,
  events = ['INSERT'],
  filter,
  onChange,
  enabled = true,
  onStatusChange,
}: UseRealtimeRefreshOptions): void {
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const onStatusChangeRef = useRef(onStatusChange);
  onStatusChangeRef.current = onStatusChange;

  const eventsKey = events.join(',');

  useEffect(() => {
    if (!enabled) return;

    const supabase = createSupabaseBrowserClient();
    const channel = supabase.channel(`realtime:${table}:${filter ?? 'all'}:${eventsKey}`);

    for (const event of eventsKey.split(',') as RealtimeEvent[]) {
      channel.on(
        'postgres_changes' as never,
        { event, schema: 'public', table, filter } as never,
        () => onChangeRef.current(),
      );
    }

    channel.subscribe((status) => {
      onStatusChangeRef.current?.(status as 'SUBSCRIBED' | 'CLOSED' | 'CHANNEL_ERROR' | 'TIMED_OUT');
    });

    return () => {
      onStatusChangeRef.current?.('CLOSED');
      supabase.removeChannel(channel);
    };
  }, [table, filter, enabled, eventsKey]);
}
