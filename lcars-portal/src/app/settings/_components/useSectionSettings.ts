'use client';

// Shared fetch/save behaviour for every server-persisted Settings section
// (HQ Behaviour, Follow-through, Intelligence, AI & Automation, Data &
// Privacy — everything backed by /api/settings). Appearance doesn't use
// this (it's local-only, lib/theme.ts / lib/motion.ts); Connections
// doesn't either (read-only, /api/settings/connections).
//
// Mission §24/§25: immediate save on change, a visible Saved✓/Saving/error
// state (never a silent write), optimistic update with the server's
// merged value as the final source of truth.

import { useCallback, useEffect, useRef, useState } from 'react';
import { DEFAULT_SETTINGS, type HqSettings } from '@/lib/settings';

export type SaveStatus = 'loading' | 'idle' | 'saving' | 'saved' | 'error';

export function useSectionSettings<K extends keyof HqSettings>(section: K) {
  const [value, setValueState] = useState<HqSettings[K]>(DEFAULT_SETTINGS[section]);
  const [status, setStatus] = useState<SaveStatus>('loading');
  const savedTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/settings')
      .then((res) => {
        if (!res.ok) throw new Error(`load failed (${res.status})`);
        return res.json();
      })
      .then((body: { settings: HqSettings }) => {
        if (cancelled) return;
        setValueState(body.settings[section]);
        setStatus('idle');
      })
      .catch(() => {
        if (!cancelled) setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [section]);

  const save = useCallback(
    async (next: HqSettings[K]) => {
      const previous = value;
      setValueState(next); // optimistic — reverted below if the write fails
      setStatus('saving');
      try {
        const res = await fetch('/api/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ [section]: next }),
        });
        if (!res.ok) throw new Error(`save failed (${res.status})`);
        const body: { settings: HqSettings } = await res.json();
        setValueState(body.settings[section]);
        setStatus('saved');
        if (savedTimeout.current) clearTimeout(savedTimeout.current);
        savedTimeout.current = setTimeout(() => setStatus('idle'), 2500);
      } catch {
        setValueState(previous);
        setStatus('error');
      }
    },
    [section, value],
  );

  useEffect(
    () => () => {
      if (savedTimeout.current) clearTimeout(savedTimeout.current);
    },
    [],
  );

  return { value, status, save };
}
