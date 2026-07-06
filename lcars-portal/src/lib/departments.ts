import type { DepartmentKey, StatusTone, StateTone } from './types';

/**
 * Department colour registry. Tailwind class fragments are listed explicitly
 * (not interpolated) so they survive Tailwind's content scan / purge.
 */
export interface DepartmentTheme {
  key: DepartmentKey;
  label: string;
  colorName: string;
  hex: string;
  text: string;
  bg: string;
  bgSoft: string;
  border: string;
  ring: string;
}

export const DEPARTMENTS: Record<DepartmentKey, DepartmentTheme> = {
  command: {
    key: 'command',
    label: 'Command',
    colorName: 'Command Gold',
    hex: '#FFB81C',
    text: 'text-command-on',
    bg: 'bg-command',
    bgSoft: 'bg-command/15',
    border: 'border-command',
    ring: 'ring-command'
  },
  engineering: {
    key: 'engineering',
    label: 'Engineering',
    colorName: 'Engineering Orange',
    hex: '#FF9800',
    text: 'text-engineering-on',
    bg: 'bg-engineering',
    bgSoft: 'bg-engineering/15',
    border: 'border-engineering',
    ring: 'ring-engineering'
  },
  operations: {
    key: 'operations',
    label: 'Operations',
    colorName: 'Operations Red',
    hex: '#F44336',
    text: 'text-operations-on',
    bg: 'bg-operations',
    bgSoft: 'bg-operations/15',
    border: 'border-operations',
    ring: 'ring-operations'
  },
  medical: {
    key: 'medical',
    label: 'Medical',
    colorName: 'Medical Blue',
    hex: '#0099FF',
    text: 'text-medical-on',
    bg: 'bg-medical',
    bgSoft: 'bg-medical/15',
    border: 'border-medical',
    ring: 'ring-medical'
  },
  science: {
    key: 'science',
    label: 'Science',
    colorName: 'Science Purple',
    hex: '#CC88FF',
    text: 'text-science-on',
    bg: 'bg-science',
    bgSoft: 'bg-science/15',
    border: 'border-science',
    ring: 'ring-science'
  },
  status: {
    key: 'status',
    label: 'Status',
    colorName: 'Status Green',
    hex: '#1B5E20', // Phase 1F: re-shaded from #4CAF50 (failed 3:1/4.5:1) — see tailwind.config.ts
    text: 'text-status-on',
    bg: 'bg-status',
    bgSoft: 'bg-status/15',
    border: 'border-status',
    ring: 'ring-status'
  }
};

/** Map a status tone (incl. neutral) to text/border/dot classes. */
export function toneClasses(tone: StatusTone): { text: string; border: string; bg: string; dot: string } {
  if (tone === 'neutral') {
    return { text: 'text-lcars-muted', border: 'border-edge', bg: 'bg-edge/30', dot: 'bg-lcars-muted' };
  }
  const d = DEPARTMENTS[tone];
  return { text: d.text, border: d.border, bg: d.bgSoft, dot: d.bg };
}

/**
 * Operational state classes (MSN-0315 Phase 1B) — decoupled from department
 * identity colour. Use for confidence/health/live-data/escalation state;
 * never repurpose a department colour to mean "state" (that conflation is
 * exactly what these tokens replace).
 */
const STATE_CLASSES: Record<StateTone, { text: string; border: string; bg: string; dot: string; on: string }> = {
  ok:      { text: 'text-state-ok',      border: 'border-state-ok',      bg: 'bg-state-ok/15',      dot: 'bg-state-ok',      on: 'text-state-ok-on' },
  warn:    { text: 'text-state-warn',    border: 'border-state-warn',    bg: 'bg-state-warn/15',    dot: 'bg-state-warn',    on: 'text-state-warn-on' },
  crit:    { text: 'text-state-crit',    border: 'border-state-crit',    bg: 'bg-state-crit/15',    dot: 'bg-state-crit',    on: 'text-state-crit-on' },
  unknown: { text: 'text-state-unknown', border: 'border-state-unknown', bg: 'bg-state-unknown/15', dot: 'bg-state-unknown', on: 'text-state-unknown-on' },
};

/** Map a state tone to text/border/bg/dot classes, plus a high-contrast `on` variant for text on solid fills. */
export function stateToneClasses(tone: StateTone): { text: string; border: string; bg: string; dot: string; on: string } {
  return STATE_CLASSES[tone];
}
