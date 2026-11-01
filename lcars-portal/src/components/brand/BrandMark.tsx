// TJR HQ brand mark ("Connected H"), Stage 0 of the brand identity work.
// Rendered as <img>, not inline SVG: HQ's globals.css sets
// `forced-color-adjust: auto` on every element, which repaints an inline SVG
// tile in one system colour in forced-colours mode and hides the mark. An
// image is painted as authored. Not yet used anywhere in the app (Stage 2).
//
// Surface rule: the tile colour follows the surface it sits on —
// `surface="light"` gives the navy tile (light header in Read mode, white
// pages); `surface="dark"` gives the inverted (mist) tile used on the dark
// sidebar and dark headers.

export type BrandSurface = 'light' | 'dark';

export interface BrandMarkProps {
  /** Surface the tile sits on. Default 'dark' (HQ chrome is dark). */
  surface?: BrandSurface;
  /** Bare mark with no tile (mono navy on light, mono white on dark). */
  mono?: boolean;
  /** Pixel size (width = height). Default 36, the existing header slot. */
  size?: number;
  /**
   * Decorative marks (the default) have empty alt: put the accessible name on
   * the parent link or button. Pass `label` only when the mark stands alone.
   */
  label?: string;
  className?: string;
}

/** Smallest size at which the standard 3.2 stroke is used; below it, the
 * heavier favicon cuts (4.6 at 32, 6 at 16) keep the mark legible. */
export function brandMarkSrc(surface: BrandSurface, mono: boolean, size: number): string {
  if (mono) return surface === 'dark' ? '/brand/hq-icon-mono-white.svg' : '/brand/hq-icon-mono-navy.svg';
  if (surface === 'light') {
    if (size <= 20) return '/brand/hq-favicon-16.svg';
    if (size <= 32) return '/brand/hq-favicon-32.svg';
  }
  return surface === 'dark' ? '/brand/hq-icon-dark.svg' : '/brand/hq-icon-light.svg';
}

export function BrandMark({ surface = 'dark', mono = false, size = 36, label, className }: BrandMarkProps) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- fixed-colour SVG brand asset; next/image adds nothing for SVG
    <img
      src={brandMarkSrc(surface, mono, size)}
      width={size}
      height={size}
      alt={label ?? ''}
      className={className}
      style={mono ? undefined : { borderRadius: '22%' }}
      draggable={false}
    />
  );
}
