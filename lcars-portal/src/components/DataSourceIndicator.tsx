import { stateToneClasses } from '@/lib/departments';

export interface DataSourceIndicatorProps {
  live: boolean;
  loading?: boolean;
  /** 'badge' = full labeled pill (panel header actions slot). 'inline' = dot + short text for dense strips. */
  variant?: 'badge' | 'inline';
  liveLabel?: string;
  mockLabel?: string;
  loadingLabel?: string;
}

/**
 * Canonical Live/Mock data-source indicator (MSN-0315 Phase 1B). Every prior
 * duplicate (CommandStrip's dot, Delivery/HumanSystems' StatusBadge reuse,
 * ROSPanels' DataSourceBadge) is replaced by this. Uses the `state.ok`/
 * `state.unknown` tokens (never department colour), and always pairs the dot
 * with visible text — colour alone is not a permitted way to convey state
 * (MSN-0310 §4.3 "never colour alone"; CommandStrip's original dot-only
 * render violated this and is fixed here, not just carried forward).
 */
export function DataSourceIndicator({
  live,
  loading = false,
  variant = 'badge',
  liveLabel = 'Live',
  mockLabel = 'No data',
  loadingLabel = 'Loading…',
}: DataSourceIndicatorProps) {
  if (loading) {
    return <span className="text-[10px] uppercase tracking-wider text-lcars-muted animate-pulse">{loadingLabel}</span>;
  }

  const tone = live ? 'ok' : 'unknown';
  const c = stateToneClasses(tone);
  const label = live ? liveLabel : mockLabel;

  if (variant === 'inline') {
    return (
      <span className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-lcars-muted">
        <span className={`h-2 w-2 rounded-full ${c.dot} ${live ? 'animate-pulse' : ''}`} />
        {label}
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${c.text} ${c.border} ${c.bg}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot} ${live ? 'animate-pulse' : ''}`} />
      {label}
    </span>
  );
}
