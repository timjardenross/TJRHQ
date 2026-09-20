/** Tiny inline sparkline for a categorical/numeric day-by-day trend.
 *  Moved out of MedicalView.tsx (2026-08-27) into its own file so both
 *  the light inline trend context on the main workbench and the dedicated
 *  /human-systems-workbench/trends page can share one implementation.
 *  Accessible alternative (the underlying rows) is summarised in text
 *  beneath wherever this is used. */
export function Sparkline({ values }: { values: (number | null)[] }) {
  const pts = values.map((v, i) => ({ v, i })).filter((p) => p.v != null) as { v: number; i: number }[];
  if (pts.length < 2) return <span className="text-[12px] text-wb-ink2">Not enough data</span>;
  const max = Math.max(...pts.map((p) => p.v));
  const min = Math.min(...pts.map((p) => p.v));
  const span = max - min || 1;
  const w = 160;
  const h = 28;
  const n = values.length - 1 || 1;
  const path = pts
    .map((p, k) => {
      const x = (p.i / n) * w;
      const y = h - ((p.v - min) / span) * h;
      return `${k === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible" aria-hidden="true">
      <path d={path} fill="none" strokeWidth="1.5" className="stroke-wb-sage-deep" />
    </svg>
  );
}

/** Colour bucket a capacity_state bar renders in — the same three-state
 *  vocabulary capacity_checkins itself uses (green/orange/red), mapped to
 *  the theme-invariant wb-ok/warn/crit tokens per stateToneClasses()'s
 *  bg/border-pairing rule (departments.ts) rather than a fresh colour
 *  choice. */
const BAR_FILL: Record<'green' | 'orange' | 'red', string> = {
  green: 'fill-wb-ok',
  orange: 'fill-wb-warn',
  red: 'fill-wb-crit',
};

export interface CapacityTrendBarDay {
  date: string;
  /** 'green' | 'orange' | 'red' | null — capacity_checkins' own
   *  capacity_state vocabulary for that day, or null when nothing was
   *  recorded. Never fabricated for a day with no check-in. */
  state: string | null;
  /** Bar height, 0-100 — TREND_CAPACITY[state] from
   *  human-systems-workbench/trends/page.tsx, passed in rather than
   *  recomputed here so this stays one scoring source, not two. */
  score: number | null;
}

/** Restyled variant of the sparkline above for the Overview tab's
 *  "Capacity Trend — Last N days" chart (mission USS-TJR-MSN-0394 §1.1) —
 *  same file, same "tiny inline SVG, real underlying rows only" discipline
 *  as Sparkline() itself, not a new charting library or a second
 *  computation of the trend numbers. Bars for days with no recorded
 *  capacity_state render as a thin neutral tick rather than a gap, so a
 *  missed day is visible instead of silently absent. */
export function CapacityTrendBars({ days }: { days: CapacityTrendBarDay[] }) {
  const w = 260;
  const h = 64;
  const gap = 2;
  const barW = days.length > 0 ? (w - gap * (days.length - 1)) / days.length : 0;
  const recorded = days.filter((d) => d.score != null).length;

  return (
    <div>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`Capacity trend, ${recorded} of ${days.length} days recorded`}>
        {days.map((d, i) => {
          const x = i * (barW + gap);
          const score = d.score ?? 0;
          const barH = d.score != null ? Math.max((score / 100) * h, 2) : 2;
          const y = h - barH;
          const fillClass =
            d.state === 'green' || d.state === 'orange' || d.state === 'red'
              ? BAR_FILL[d.state]
              : 'fill-wb-line';
          return <rect key={d.date} x={x} y={y} width={barW} height={barH} className={fillClass} rx={1} />;
        })}
      </svg>
      <p className="mt-2 text-[11px] text-wb-ink2">
        {recorded} of {days.length} day{days.length === 1 ? '' : 's'} have a recorded capacity check-in.
      </p>
    </div>
  );
}
