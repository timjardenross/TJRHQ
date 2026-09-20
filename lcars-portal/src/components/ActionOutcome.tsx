import { useEffect } from 'react';

export function ActionOutcome({ message, tone = 'neutral' }: { message?: string | null; tone?: 'success' | 'error' | 'neutral' }) {
  useEffect(() => {
    if (!message || typeof window === 'undefined') return;
    // Consequential outcomes belong to the authenticated server audit trail.
    // Do not persist them to localStorage: that made history device-local,
    // unauditable, and easy to lose when the browser was cleared.
    void fetch('/api/action-history', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'ui_action_outcome', outcome: tone, details: { message } }),
      keepalive: true,
    }).catch(() => {
      // The visible outcome remains useful when the audit service is down;
      // the affected workbench should separately show an unavailable state.
    });
  }, [message, tone]);
  if (!message) return null;
  const classes = tone === 'success' ? 'border-wb-ok/40 bg-wb-ok/10 text-wb-ok-on' : tone === 'error' ? 'border-wb-crit/40 bg-wb-crit/10 text-wb-crit-on' : 'border-wb-line bg-wb-surface text-wb-ink2';
  return <p className={`rounded-md border px-3 py-2 text-[12px] ${classes}`} role="status" aria-live="polite">{message}</p>;
}
