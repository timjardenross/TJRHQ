import type { HqIntelItem } from './model';

export const LENSES = ['All', 'Needs you', 'Watching', 'Alerts', 'Technical', 'Health'] as const;
export type Lens = (typeof LENSES)[number];

/** Lenses are filters over one list, not separate pages. */
export function filterIntel(items: HqIntelItem[], lens: Lens): HqIntelItem[] {
  if (lens === 'All') return items;
  if (lens === 'Needs you') return items.filter((i) => i.needsYou);
  if (lens === 'Watching') return items.filter((i) => i.watching);
  return items.filter((i) => i.lens === lens);
}
