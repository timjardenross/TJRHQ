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
