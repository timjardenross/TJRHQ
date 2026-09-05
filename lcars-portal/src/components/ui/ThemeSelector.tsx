'use client';

// Adaptive Themes mission (2026-09-05), §5 — the "◐ Archive ▾" control,
// visible across every HQ surface via WorkbenchShell. Native <select>
// (same pattern WorkbenchSwitcher already uses in this file's sibling
// component) — full keyboard nav and screen-reader labelling for free,
// no custom listbox to hand-roll or a11y-audit.
import { useTheme, THEME_NAMES, THEME_LABELS } from '@/lib/theme';

export function ThemeSelector() {
  const [theme, setTheme] = useTheme();

  return (
    <label className="flex items-center gap-1 text-[12px] text-wb-ink2">
      <span aria-hidden>◐</span>
      <span className="sr-only">Theme</span>
      <select
        aria-label="Select theme"
        value={theme}
        onChange={(e) => setTheme(e.target.value as (typeof THEME_NAMES)[number])}
        className="rounded-md border border-wb-line bg-wb-surface px-2 py-1 text-[12px] text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
      >
        {THEME_NAMES.map((name) => (
          <option key={name} value={name}>{THEME_LABELS[name]}</option>
        ))}
      </select>
    </label>
  );
}
