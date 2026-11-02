/**
 * Which alerts are new since the last time we looked, for screen-reader
 * announcements. The first look (prev === null) announces nothing: arriving on
 * the page already shows the banner and the sections, and reading out every
 * standing alert on load would be noise. Only an alert that appears while the
 * page is open is announced.
 */
export function newlyAppeared<T extends { id: string }>(prev: ReadonlySet<string> | null, current: readonly T[]): T[] {
  if (prev === null) return [];
  return current.filter((a) => !prev.has(a.id));
}
