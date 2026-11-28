// HQ Workbench feature flag. Server-side only, default OFF.
//
// The new /hq workbench is a parallel presentation layer. It is switched on
// with the HQ_WORKBENCH_ENABLED environment variable and nothing else reads
// this flag, so turning it off (or never setting it) leaves every existing
// workbench exactly as it was. Read at request time, not build time: the
// /hq layout is force-dynamic, so changing the variable needs no rebuild.

const TRUE_VALUES = new Set(['1', 'true', 'yes', 'on']);

export function isHqEnabled(env: Record<string, string | undefined> = process.env): boolean {
  const raw = env.HQ_WORKBENCH_ENABLED;
  if (typeof raw !== 'string') return false;
  return TRUE_VALUES.has(raw.trim().toLowerCase());
}
