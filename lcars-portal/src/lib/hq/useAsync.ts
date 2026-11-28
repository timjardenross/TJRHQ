'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/** Minimal loader hook: runs once, exposes reload, never sets state after unmount. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const run = useCallback(async () => {
    setLoading(true);
    try {
      const v = await loaderRef.current();
      if (alive.current) { setData(v); setError(null); }
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      if (alive.current) setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    alive.current = true;
    void run();
    return () => { alive.current = false; };
  }, [run]);

  return { data, loading, error, reload: run };
}
