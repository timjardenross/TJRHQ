'use client';

import { useEffect, useState } from 'react';

// Asks the server once per page load whether HQ is switched on. Any failure
// (signed out, offline, route missing) means "not enabled", so the existing
// workbenches can never be changed by this check going wrong.
let cached: Promise<boolean> | null = null;

function fetchEnabled(): Promise<boolean> {
  if (!cached) {
    cached = fetch('/api/hq/status', { headers: { Accept: 'application/json' } })
      .then((r) => (r.ok ? r.json() : { enabled: false }))
      .then((j: { enabled?: unknown }) => j.enabled === true)
      .catch(() => false);
  }
  return cached;
}

export function useHqEnabled(): boolean {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    let alive = true;
    void fetchEnabled().then((v) => { if (alive) setEnabled(v); });
    return () => { alive = false; };
  }, []);
  return enabled;
}

/** Test seam: forget the cached answer. */
export function resetHqEnabledCache() { cached = null; }
