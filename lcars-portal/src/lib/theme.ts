'use client';

// TJR HQ adaptive theme system — 5 selectable visual environments (Archive/
// Command/Midnight/Horizon/Sanctuary), all built on the same `wb-*` Tailwind
// tokens (now CSS-variable-backed, see globals.css + tailwind.config.ts) so
// every existing *-workbench page re-themes automatically with zero call-
// site changes. A separate module from src/lib/preferences.ts (that file's
// `Preferences.theme` field was an unused single-value stub, removed —
// bundling this into that unrelated settings blob would couple two
// different concerns for no reason) but the same SSR-safe
// load/save/hook shape.
//
// Structure only changes between themes never (same sidebar, same
// workbench positions, same routes) — only the environment (colour/
// typography/motion feel) does. See docs/adaptive-themes mission brief.

import { useEffect, useState } from 'react';

export const THEME_NAMES = ['archive', 'command', 'midnight', 'horizon', 'sanctuary'] as const;
export type ThemeName = (typeof THEME_NAMES)[number];

export const THEME_LABELS: Record<ThemeName, string> = {
  archive: 'Archive',
  command: 'Command',
  midnight: 'Midnight',
  horizon: 'Horizon',
  sanctuary: 'Sanctuary',
};

// Decorative, theme-specific secondary phrase for the Home welcome header
// (mission brief §9) — intentionally small/optional, never load-bearing.
export const THEME_TAGLINE: Record<ThemeName, string> = {
  archive: 'Progress over perfection.',
  command: 'Clarity drives capacity.',
  midnight: 'A calmer mind. A clearer tomorrow.',
  horizon: 'More capacity for a brighter tomorrow.',
  sanctuary: 'A quieter space. A stronger you.',
};

export const DEFAULT_THEME: ThemeName = 'archive';
const STORAGE_KEY = 'tjr-hq-theme';

function isThemeName(value: unknown): value is ThemeName {
  return typeof value === 'string' && (THEME_NAMES as readonly string[]).includes(value);
}

export function loadTheme(): ThemeName {
  if (typeof window === 'undefined') return DEFAULT_THEME;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return isThemeName(raw) ? raw : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

export function applyTheme(theme: ThemeName): void {
  if (typeof document === 'undefined') return;
  document.documentElement.dataset.theme = theme;
}

export function saveTheme(theme: ThemeName): void {
  applyTheme(theme);
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // localStorage unavailable — theme still applied for this page view,
    // just won't persist across a reload.
  }
}

/** Hydrates from localStorage on mount (the inline anti-flash script in
 * layout.tsx already set the DOM attribute before hydration — this just
 * brings React state in sync with it) and exposes a setter that updates
 * both the DOM attribute and localStorage together. */
export function useTheme(): [ThemeName, (t: ThemeName) => void] {
  const [theme, setThemeState] = useState<ThemeName>(DEFAULT_THEME);

  useEffect(() => {
    setThemeState(loadTheme());
  }, []);

  function setTheme(t: ThemeName) {
    saveTheme(t);
    setThemeState(t);
  }

  return [theme, setTheme];
}
