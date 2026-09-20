export function ActionOutcome({ message, tone = 'neutral' }: { message?: string | null; tone?: 'success' | 'error' | 'neutral' }) {
  if (!message) return null;
  const classes = tone === 'success' ? 'border-wb-ok/40 bg-wb-ok/10 text-wb-ok-on' : tone === 'error' ? 'border-wb-crit/40 bg-wb-crit/10 text-wb-crit-on' : 'border-wb-line bg-wb-surface text-wb-ink2';
  return <p className={`rounded-md border px-3 py-2 text-[12px] ${classes}`} role="status" aria-live="polite">{message}</p>;
}
