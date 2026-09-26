'use client';

// Mission §3/§4 — Appearance controls the persistent visual experience.
// Motion (lib/motion.ts) is the one remaining user-facing appearance
// control (mission §3's "Motion: Reduced/Standard").
//
// Endeavour 27 (USS-TJR-MSN-0394): the 5-theme selector this section used
// to expose (lib/theme.ts, ThemeSelector.tsx) is retired — Captain-
// confirmed decision, "One fixed dark Command/Focus identity + Read as a
// contextual light surface... not 5 independently-selectable whole-app
// palettes." Reading mode is now a per-page classification
// (WorkbenchShell's `mode` prop), not a Captain-facing setting.
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
import { useMotion, MOTION_NAMES, MOTION_LABELS } from '@/lib/motion';

export function AppearanceSection() {
  const [motion, setMotion] = useMotion();
  const [savedFlash, setSavedFlash] = useState<'motion' | null>(null);

  useEffect(() => {
    if (!savedFlash) return;
    const t = setTimeout(() => setSavedFlash(null), 2000);
    return () => clearTimeout(t);
  }, [savedFlash]);

  return (
    <div>
      <SectionHeading title="Appearance" description="Control the persistent visual experience across TJR HQ." />
      <div className="rounded-lg border border-wb-line bg-wb-surface px-4">
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
