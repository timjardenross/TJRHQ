'use client';

import { useState, useEffect } from 'react';

export interface Preferences {
  operatingMode: 'Health' | 'Work' | 'Recovery' | 'Build' | 'Travel';
  favouritePages: string[];
  quietHoursStart: string;
  quietHoursEnd: string;
  defaultAdvisor: 'xo' | 'cmo' | 'cto' | 'cdo' | 'strategic' | 'staff-briefing';
  briefingTime: string;
  notifyTelegram: boolean;
  notifyInApp: boolean;
  theme: 'dark';
}

const DEFAULTS: Preferences = {
  operatingMode: 'Work',
  favouritePages: ['/captains-chair-workbench', '/missions', '/captains-log'],
  quietHoursStart: '22:00',
  quietHoursEnd: '07:00',
  defaultAdvisor: 'xo',
  briefingTime: '07:00',
  notifyTelegram: true,
  notifyInApp: true,
  theme: 'dark',
};

const STORAGE_KEY = 'lcars-prefs';

export function loadPrefs(): Preferences {
  if (typeof window === 'undefined') return { ...DEFAULTS };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULTS };
    const parsed = JSON.parse(raw);
    return { ...DEFAULTS, ...parsed };
  } catch {
    return { ...DEFAULTS };
  }
}

export function savePrefs(p: Preferences): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
  } catch {
    // localStorage unavailable
  }
}

export function updatePref<K extends keyof Preferences>(key: K, value: Preferences[K]): Preferences {
  const current = loadPrefs();
  const updated = { ...current, [key]: value };
  savePrefs(updated);
  return updated;
}

export function usePrefs(): [Preferences, (p: Preferences) => void] {
  const [prefs, setPrefsState] = useState<Preferences>({ ...DEFAULTS });

  useEffect(() => {
    setPrefsState(loadPrefs());
  }, []);

  const setPrefs = (p: Preferences) => {
    savePrefs(p);
    setPrefsState(p);
  };

  return [prefs, setPrefs];
}
