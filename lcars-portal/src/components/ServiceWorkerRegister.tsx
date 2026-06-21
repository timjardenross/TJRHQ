'use client';

import { useEffect } from 'react';

/**
 * Registers the PWA service worker (MSN-IOS-001 WP1). Mounted once in the root
 * layout. Registration failures are non-fatal — the portal works without it.
 */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
    const register = () => {
      navigator.serviceWorker.register('/sw.js').catch(() => {
        /* SW registration is best-effort */
      });
    };
    if (document.readyState === 'complete') register();
    else window.addEventListener('load', register, { once: true });
  }, []);

  return null;
}
