'use client';

import { useEffect, useRef } from 'react';

// Screen Wake Lock API (Safari 16.4+, Chrome/Edge, no Firefox as of this
// writing) — keeps the display awake while this page is open, so an
// always-on wall-tablet use (LifeOS Hub, docs/LifeOS-Wall-Tablet-V1-
// Component-Scope.md) doesn't rely on someone remembering to set
// Auto-Lock to Never in Settings. Best-effort only: unsupported browsers
// silently no-op, and this is deliberately not a substitute for the
// device-side setup (Auto-Lock/Guided Access/Configurator kiosk mode) —
// just one less thing to misconfigure.
//
// The lock is released automatically by the browser whenever the page
// is backgrounded/hidden (tab-switched, screen manually locked) — this
// re-acquires it on the next 'visibilitychange' back to visible, which
// is the standard pattern every Wake Lock API guide recommends, since
// there's no way to keep the lock held through a background period.
export function useWakeLock(): void {
  const lockRef = useRef<WakeLockSentinel | null>(null);

  useEffect(() => {
    if (typeof navigator === 'undefined' || !('wakeLock' in navigator)) return;

    let cancelled = false;

    async function acquire() {
      try {
        const lock = await navigator.wakeLock.request('screen');
        if (cancelled) {
          // Component unmounted while the request was in flight.
          lock.release().catch(() => {});
          return;
        }
        lockRef.current = lock;
      } catch (err) {
        // Common, non-actionable causes: tab not visible yet, low battery
        // on some platforms, permissions policy. Not worth surfacing to
        // the Captain — this is a best-effort enhancement, not a feature
        // the page depends on.
        console.warn('[useWakeLock] request failed:', err);
      }
    }

    function onVisibilityChange() {
      if (document.visibilityState === 'visible' && !lockRef.current) {
        acquire();
      }
    }

    acquire();
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', onVisibilityChange);
      lockRef.current?.release().catch(() => {});
      lockRef.current = null;
    };
  }, []);
}
