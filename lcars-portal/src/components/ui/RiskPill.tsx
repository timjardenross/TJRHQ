'use client';

// RED/AMBER/GREEN/HIGH/MEDIUM/LOW -> tint className/badge. Extracted from
// intelligence-workbench/_components/Shell.tsx (WORKBENCH-REVIEW.md H9/H12,
// 2026-07-18) - risk/severity rendering is unrelated to page-shell layout,
// it only ended up bundled there because intelligence-workbench happened to
// be the first workbench built. Every other workbench importing it had to
// reach into intelligence-workbench's own folder to get it.

import { Badge, riskToStatus } from './Badge';

const STATUS_TINT_CLASSES: Record<ReturnType<typeof riskToStatus>, string> = {
  error: 'bg-wb-crit/15 text-wb-crit-on',
  warning: 'bg-wb-warn/15 text-wb-warn-on',
  success: 'bg-wb-ok/15 text-wb-ok-on',
  info: 'bg-wb-sage/15 text-wb-sage-deep',
  neutral: 'bg-wb-line text-wb-ink2',
};

/** RED/AMBER/GREEN/HIGH/MEDIUM/LOW -> tint className. Kept for callers composing custom elements. */
export function riskClass(r: string | null | undefined) {
  return STATUS_TINT_CLASSES[riskToStatus(r)];
}

export function RiskPill({ value }: { value: string | null | undefined }) {
  return <Badge status={riskToStatus(value)}>{value ?? '—'}</Badge>;
}
