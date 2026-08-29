'use client';

// RED/AMBER/GREEN/HIGH/MEDIUM/LOW -> tint className/badge. Extracted from
// intelligence-workbench/_components/Shell.tsx (WORKBENCH-REVIEW.md H9/H12,
// 2026-07-18) - risk/severity rendering is unrelated to page-shell layout,
// it only ended up bundled there because intelligence-workbench happened to
// be the first workbench built. Every other workbench importing it had to
// reach into intelligence-workbench's own folder to get it.

import { Badge, riskToStatus, STATUS_CLASSES } from './Badge';

/** RED/AMBER/GREEN/HIGH/MEDIUM/LOW -> tint className. Kept for callers
 *  composing custom elements. 2026-08-29: no longer its own duplicate of
 *  Badge's color table — reuses STATUS_CLASSES directly. */
export function riskClass(r: string | null | undefined) {
  return STATUS_CLASSES[riskToStatus(r)];
}

export function RiskPill({ value }: { value: string | null | undefined }) {
  return <Badge status={riskToStatus(value)}>{value ?? '—'}</Badge>;
}
