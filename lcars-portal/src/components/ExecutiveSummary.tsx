import type { StateTone } from '@/lib/types';
import { stateToneClasses } from '@/lib/departments';
import { RecommendationCard, type RecommendedAction } from './RecommendationCard';

export interface ShipStatusItem {
  key: string;
  label: string;
  state: string;
  /** Health/state tone, not department identity — see StateTone's doc
   *  comment in ./types. Was StatusTone (design-audit finding: routed
   *  through toneClasses(), which flattens every non-neutral value to one
   *  navy since 2026-07-10 — tiles never colour-coded even when critical). */
  tone: StateTone;
  trend?: 'up' | 'down' | 'steady';
  detail?: string;
}

const TREND_GLYPH = { up: '▲', down: '▼', steady: '▬' } as const;

export interface ExecutiveSummaryProps {
  recommendation: RecommendedAction | null;
  isLoading?: boolean;
  isLive?: boolean;
  recommendationTitle?: string;
  shipStatus: ShipStatusItem[];
  statusTitle?: string;
  emptyStatusMessage?: string;
  loadingStatusMessage?: string;
  /**
   * Compact renders the denser mobile tile grid (dot + label + state only,
   * capped to 6 tiles, no trend glyph / detail line). Desktop shows the full
   * grid with trend + detail.
   */
  compact?: boolean;
}

/**
 * Canonical "headline action + supporting tiles" composite (MSN-0315 Phase
 * 1B), per MSN-0303's ratified finding: CommandStrip (desktop) and
 * MobileOperatingPicture (mobile) independently coded the same recommended-
 * action headline + ship-status tile grid over the same useCommandCentre
 * hook. The headline is RecommendationCard; the tile grid is formalized here.
 * Mobile's additional sections (decision banner, capacity, escalations,
 * blocked-work) are NOT part of this ratified duplicate and stay owned by
 * MobileOperatingPicture.
 */
export function ExecutiveSummary({
  recommendation,
  isLoading = false,
  isLive,
  recommendationTitle,
  shipStatus,
  statusTitle = 'Ship Status',
  emptyStatusMessage = 'Status awaiting data.',
  loadingStatusMessage = 'Reading ship status…',
  compact = false,
}: ExecutiveSummaryProps) {
  const items = compact ? shipStatus.slice(0, 6) : shipStatus;

  return (
    <div className="flex flex-col gap-3">
      <RecommendationCard
        recommendation={recommendation}
        isLoading={isLoading}
        isLive={isLive}
        title={recommendationTitle}
        compact={compact}
      />

      <div className={`rounded-lcars border border-edge bg-panel/60 ${compact ? 'p-4' : 'p-3'}`}>
        <p
          className={`mb-2 text-[10px] uppercase tracking-[0.25em] text-lcars-muted ${compact ? 'tracking-[0.3em]' : 'font-bold'}`}
        >
          {statusTitle}
        </p>
        {items.length > 0 ? (
          <div className={compact ? 'grid grid-cols-2 gap-2' : 'grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6'}>
            {items.map((d) => {
              const c = stateToneClasses(d.tone);
              if (compact) {
                return (
                  <div key={d.key} className="rounded-md border border-edge bg-panel-2/60 p-2">
                    <div className="flex items-center gap-1.5">
                      <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
                      <span className="text-[10px] uppercase tracking-wide text-lcars-muted">{d.label}</span>
                    </div>
                    <p className={`mt-0.5 text-xs font-bold ${c.text}`}>{d.state}</p>
                  </div>
                );
              }
              return (
                <div key={d.key} className={`rounded-md border ${c.border} bg-panel-2/60 p-2`}>
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] uppercase tracking-wide text-lcars-muted">{d.label}</span>
                    {d.trend && <span className={`text-[10px] ${c.text}`}>{TREND_GLYPH[d.trend]}</span>}
                  </div>
                  <p className={`mt-1 font-lcars text-sm font-bold ${c.text}`}>{d.state}</p>
                  {d.detail && <p className="mt-0.5 text-[10px] leading-tight text-lcars-muted">{d.detail}</p>}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-[11px] text-lcars-muted">{isLoading ? loadingStatusMessage : emptyStatusMessage}</p>
        )}
      </div>
    </div>
  );
}
