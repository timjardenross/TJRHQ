import { stateToneClasses } from '@/lib/departments';

export type OperationalState = 'nominal' | 'degraded' | 'attention' | 'unavailable';

const COPY: Record<OperationalState, { label: string; tone: 'ok' | 'warn' | 'crit' | 'unknown' }> = {
  nominal: { label: 'Nominal', tone: 'ok' },
  degraded: { label: 'Degraded', tone: 'warn' },
  attention: { label: 'Attention', tone: 'crit' },
  unavailable: { label: 'Unavailable', tone: 'unknown' },
};

export function OperationalStateBadge({ state }: { state: OperationalState }) {
  const copy = COPY[state];
  const tones = stateToneClasses(copy.tone);
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] ${tones.border} ${tones.bg} ${tones.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${tones.dot}`} aria-hidden />
      {copy.label}
    </span>
  );
}
