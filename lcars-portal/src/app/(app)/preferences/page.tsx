'use client';

import { useState, useEffect } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { usePrefs, updatePref, type Preferences } from '@/lib/preferences';

const MODE_DESCRIPTIONS: Record<Preferences['operatingMode'], string> = {
  Health: 'Recovery-led. Protect capacity, minimise cognitive load.',
  Work: 'Standard operations. Full mission and decision engagement.',
  Recovery: 'Intensive recovery. Limit non-essential tasks.',
  Build: 'Deep work focus. USS TJR engineering and development.',
  Travel: 'Mobile operations. Essential comms and decisions only.',
};

const MODES: Preferences['operatingMode'][] = ['Health', 'Work', 'Recovery', 'Build', 'Travel'];

const ADVISORS: { value: Preferences['defaultAdvisor']; label: string }[] = [
  { value: 'xo', label: 'XO' },
  { value: 'cmo', label: 'CMO' },
  { value: 'cto', label: 'CTO' },
  { value: 'cdo', label: 'CDO' },
  { value: 'strategic', label: 'Strategic' },
  { value: 'staff-briefing', label: 'Staff Briefing' },
];

const PAGES: { href: string; label: string }[] = [
  { href: '/captains-chair', label: "Captain's Chair" },
  { href: '/missions', label: 'Missions' },
  { href: '/captains-log', label: "Captain's Log" },
  { href: '/medical', label: 'Medical' },
  { href: '/intelligence', label: 'Intelligence' },
  { href: '/chief-of-staff', label: 'Chief of Staff' },
  { href: '/timeline', label: 'Timeline' },
  { href: '/search', label: 'Search' },
  { href: '/knowledge', label: 'Knowledge' },
  { href: '/capture', label: 'Quick Capture' },
];

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!on)}
      className={`relative inline-flex h-6 w-11 rounded-full transition-colors focus:outline-none ${on ? 'bg-science' : 'bg-edge'}`}
      aria-pressed={on}
    >
      <span
        className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform mt-0.5 ${on ? 'translate-x-5' : 'translate-x-0.5'}`}
      />
    </button>
  );
}

export default function PreferencesPage() {
  const [prefs, setPrefs] = usePrefs();
  const [saved, setSaved] = useState(false);

  function flash() {
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  function save<K extends keyof Preferences>(key: K, value: Preferences[K]) {
    const updated = updatePref(key, value);
    setPrefs(updated);
    flash();
  }

  function toggleFavourite(href: string) {
    const current = prefs.favouritePages;
    const next = current.includes(href)
      ? current.filter((h) => h !== href)
      : [...current, href];
    save('favouritePages', next);
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <LCARSPanel title="Preferences" accent="command" eyebrow="MSN-3D-001 · Personalisation">
        <div className="flex items-center justify-between py-2">
          <p className="text-lcars-muted text-sm">Changes are saved automatically.</p>
          <span
            className={`text-sm font-lcars text-science transition-opacity duration-300 ${saved ? 'opacity-100' : 'opacity-0'}`}
          >
            Preferences saved
          </span>
        </div>
      </LCARSPanel>

      {/* Operating Mode */}
      <LCARSPanel title="Operating Mode" accent="science" eyebrow="Current operational context">
        <div className="space-y-4 py-2">
          <div className="flex flex-wrap gap-2">
            {MODES.map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => save('operatingMode', mode)}
                className={`px-4 py-2 rounded-lcars font-lcars text-sm transition-colors ${
                  prefs.operatingMode === mode
                    ? 'bg-science text-space'
                    : 'border border-edge text-lcars-text hover:border-science hover:text-science'
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
          <p className="text-lcars-muted text-sm">{MODE_DESCRIPTIONS[prefs.operatingMode]}</p>
        </div>
      </LCARSPanel>

      {/* Favourite Pages */}
      <LCARSPanel title="Favourite Pages" accent="science" eyebrow="Quick access">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 py-2">
          {PAGES.map(({ href, label }) => {
            const checked = prefs.favouritePages.includes(href);
            return (
              <label
                key={href}
                className="flex items-center gap-3 cursor-pointer group"
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleFavourite(href)}
                  className="accent-science h-4 w-4 rounded"
                />
                <span className={`text-sm ${checked ? 'text-lcars-text' : 'text-lcars-muted'} group-hover:text-lcars-text transition-colors`}>
                  {label}
                </span>
              </label>
            );
          })}
        </div>
      </LCARSPanel>

      {/* Notification Preferences */}
      <LCARSPanel title="Notification Preferences" accent="operations" eyebrow="Alert routing">
        <div className="space-y-4 py-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-lcars-text">Telegram notifications</span>
            <Toggle
              on={prefs.notifyTelegram}
              onChange={(v) => save('notifyTelegram', v)}
            />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-lcars-text">In-app notifications</span>
            <Toggle
              on={prefs.notifyInApp}
              onChange={(v) => save('notifyInApp', v)}
            />
          </div>
          <div className="border-t border-edge pt-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-lcars-text">Quiet hours start</span>
              <input
                type="time"
                value={prefs.quietHoursStart}
                onChange={(e) => save('quietHoursStart', e.target.value)}
                className="bg-panel border border-edge rounded text-lcars-text text-sm px-2 py-1 focus:outline-none focus:border-operations"
              />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-lcars-text">Quiet hours end</span>
              <input
                type="time"
                value={prefs.quietHoursEnd}
                onChange={(e) => save('quietHoursEnd', e.target.value)}
                className="bg-panel border border-edge rounded text-lcars-text text-sm px-2 py-1 focus:outline-none focus:border-operations"
              />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-lcars-text">Briefing time</span>
              <input
                type="time"
                value={prefs.briefingTime}
                onChange={(e) => save('briefingTime', e.target.value)}
                className="bg-panel border border-edge rounded text-lcars-text text-sm px-2 py-1 focus:outline-none focus:border-operations"
              />
            </div>
          </div>
        </div>
      </LCARSPanel>

      {/* Default Advisor */}
      <LCARSPanel title="Default Advisor" accent="science" eyebrow="Executive Staff">
        <div className="flex flex-wrap gap-2 py-2">
          {ADVISORS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              onClick={() => save('defaultAdvisor', value)}
              className={`px-4 py-2 rounded-lcars font-lcars text-sm transition-colors ${
                prefs.defaultAdvisor === value
                  ? 'bg-science text-space'
                  : 'border border-edge text-lcars-text hover:border-science hover:text-science'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </LCARSPanel>
    </div>
  );
}
