// TJR HQ wordmark lockups (outlined SVG, no live text). `<img>` for the same
// forced-colours reason as BrandMark. Not yet used in the app (Stage 2).
import type { BrandSurface } from './BrandMark';

export type WordmarkLayout = 'primary' | 'horizontal' | 'compact';

/** Natural aspect ratio (width / height) of each lockup, from the SVG viewBox. */
export const WORDMARK_ASPECT: Record<WordmarkLayout, number> = {
  primary: 1280.85 / 180,
  horizontal: 686.32 / 180,
  compact: 446.32 / 78,
};

/** Minimum rendered width in px. The primary lockup carries the descriptor,
 * which must stay at or above 12 px, hence 310. */
export const WORDMARK_MIN_WIDTH: Record<WordmarkLayout, number> = {
  primary: 310,
  horizontal: 160,
  compact: 72,
};

interface BrandWordmarkBaseProps {
  surface?: BrandSurface;
  /** Rendered width in px; clamped up to the layout's minimum. */
  width?: number;
  /** Accessible name. Default "TJR HQ"; pass '' when a sibling already names it. */
  label?: string;
  className?: string;
}

/**
 * Mono exists only in the horizontal footprint (bare mark + TJR | HQ), so the
 * type forbids combining `mono` with the primary or compact layouts instead of
 * silently substituting a different footprint.
 */
export type BrandWordmarkProps = BrandWordmarkBaseProps &
  (
    | { layout?: WordmarkLayout; mono?: false }
    | { layout?: 'horizontal'; /** Single-colour lockup without a tile (navy on light, white on dark). */ mono: true }
  );

export function brandWordmarkSrc(layout: WordmarkLayout, surface: BrandSurface, mono: boolean): string {
  if (mono) {
    // Mono exists for the tile lockup only; compact is already text-only.
    return surface === 'dark' ? '/brand/hq-wordmark-mono-white.svg' : '/brand/hq-wordmark-mono-navy.svg';
  }
  return `/brand/hq-wordmark-${layout}-${surface}.svg`;
}

export function BrandWordmark({
  layout = 'horizontal',
  surface = 'dark',
  mono = false,
  width,
  label = 'TJR HQ',
  className,
}: BrandWordmarkProps) {
  const w = Math.max(width ?? WORDMARK_MIN_WIDTH[layout] * 1.5, WORDMARK_MIN_WIDTH[layout]);
  const aspect = mono ? 582.88 / 180 : WORDMARK_ASPECT[layout];
  return (
    // eslint-disable-next-line @next/next/no-img-element -- fixed-colour SVG brand asset
    <img
      src={brandWordmarkSrc(layout, surface, mono)}
      width={Math.round(w)}
      height={Math.round(w / aspect)}
      alt={label}
      className={className}
      draggable={false}
    />
  );
}
