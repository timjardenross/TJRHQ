'use client';

// Mission §3/§4 — Appearance controls the persistent visual experience,
// using HQ's EXISTING global theme implementation (lib/theme.ts, already
// live across every *-workbench page via WorkbenchShell/ThemeSelector) and
// its motion counterpart (lib/motion.ts). No second theme engine here —
// this section is a thin, discoverable home for controls that already
// exist as a header dropdown, plus one small uplift (a manual motion
// override, mission §3's "Motion: Reduced/Standard").
//
// Interface density (Calm/Comfortable/Compact) is explicitly NOT built:
// the audit found no global density/spacing-scale system to hook into, and
// mission §3 is explicit — "classify it as FUTURE... rather than
// implementing a competing style system." Fabricating a control with
// nothing behind it would violate mission §28's "do not fabricate
// settings that cannot actually be persisted or applied."
import { useEffect, useState } from 'react';
import { SectionHeading, SettingRow } from './SectionHeading';
import { Select } from '@/components/ui/Input';
import { useTheme, THEME_NAMES, THEME_LABELS } from '@/lib/theme';
import { useMotion, MOTION_NAMES, MOTION_LABELS } from '@/lib/motion';

export function AppearanceSection() {
  const [theme, setTheme] = useTheme();
  const [motion, setMotion] = useMotion();
  const [savedFlash, setSavedFlash] = useState<'theme' | 'motion' | null>(null);

  useEffect(() => {
    if (!savedFlash) return;
    const t = setTimeout(() => setSavedFlash(null), 2000);
    return () => clearTimeout(t);
  }, [savedFlash]);

  return (
    <div>
      <SectionHeading title="Appearance" description="Control the persistent visual experience across TJR HQ." />
      <div className="rounded-lg border border-wb-line bg-wb-surface px-4">
        <SettingRow label="Theme" hint="One of five shared HQ themes — applies everywhere, immediately.">
          <div className="flex items-center gap-2">
            <Select
              aria-label="Theme"
              value={theme}
              onChange={(e) => {
                setTheme(e.target.value as (typeof THEME_NAMES)[number]);
                setSavedFlash('theme');
              }}
              className="min-w-[140px]"
            >
              {THEME_NAMES.map((name) => (
                <option key={name} value={name}>
                  {THEME_LABELS[name]}
                </option>
              ))}
            </Select>
            {savedFlash === 'theme' && <span className="text-[12px] font-medium text-wb-ok-on">Saved ✓</span>}
          </div>
        </SettingRow>
        <SettingRow label="Motion" hint="Reduced turns off HQ's own transitions and animations, regardless of your device's own setting.">
          <div className="flex items-center gap-2">
            <Select
              aria-label="Motion"
              value={motion}
              onChange={(e) => {
                setMotion(e.target.value as (typeof MOTION_NAMES)[number]);
                setSavedFlash('motion');
              }}
              className="min-w-[140px]"
            >
              {MOTION_NAMES.map((name) => (
                <option key={name} value={name}>
                  {MOTION_LABELS[name]}
                </option>
              ))}
            </Select>
            {savedFlash === 'motion' && <span className="text-[12px] font-medium text-wb-ok-on">Saved ✓</span>}
          </div>
        </SettingRow>
      </div>
      <p className="mt-3 text-[12px] text-wb-ink2">
        Interface density (Calm / Comfortable / Compact) isn&apos;t available yet — HQ doesn&apos;t have a shared density system to
        plug into today, so this stays off Settings rather than offering a control that wouldn&apos;t do anything.
      </p>
    </div>
  );
}
