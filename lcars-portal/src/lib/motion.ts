'use client';

// TJR HQ Settings Page Redesign mission, Appearance §3 — a manual "Reduced"
// override on top of the OS-level prefers-reduced-motion media query that
// globals.css already honours unconditionally. Same SSR-safe load/save/hook
// shape as lib/theme.ts (a deliberately separate module, same reasoning as
// that file's own separation from lib/preferences.ts: different concern,
// same shape) — device-local, localStorage-backed, no server round trip
// needed for a value this low-stakes.

import { useEffect, useState } from 'react';

export const MOTION_NAMES = ['standard', 'reduced'] as const;
export type MotionName = (typeof MOTION_NAMES)[number];

export const MOTION_LABELS: Record<MotionName, string> = {
  standard: 'Standard',
  reduced: 'Reduced',
};

export const DEFAULT_MOTION: MotionName = 'standard';
const STORAGE_KEY = 'tjr-hq-motion';

function isMotionName(value: unknown): value is MotionName {
  return typeof value === 'string' && (MOTION_NAMES as readonly string[]).includes(value);
}

export function loadMotion(): MotionName {
  if (typeof window === 'undefined') return DEFAULT_MOTION;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return isMotionName(raw) ? raw : DEFAULT_MOTION;
  } catch {
    return DEFAULT_MOTION;
  }
}

export function applyMotion(motion: MotionName): void {
  if (typeof document === 'undefined') return;
  document.documentElement.dataset.motion = motion;
}

export function saveMotion(motion: MotionName): void {
  applyMotion(motion);
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, motion);
  } catch {
    // localStorage unavailable — still applied for this page view.
  }
}

export function useMotion(): [MotionName, (m: MotionName) => void] {
  const [motion, setMotionState] = useState<MotionName>(DEFAULT_MOTION);

  useEffect(() => {
    setMotionState(loadMotion());
  }, []);

  function setMotion(m: MotionName) {
    saveMotion(m);
    setMotionState(m);
  }

  return [motion, setMotion];
}
