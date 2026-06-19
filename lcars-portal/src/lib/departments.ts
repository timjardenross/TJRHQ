import type { DepartmentKey, StatusTone } from './types';

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
    text: 'text-command',
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
    text: 'text-engineering',
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
    text: 'text-operations',
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
    text: 'text-medical',
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
    text: 'text-science',
    bg: 'bg-science',
    bgSoft: 'bg-science/15',
    border: 'border-science',
    ring: 'ring-science'
  },
  status: {
    key: 'status',
    label: 'Status',
    colorName: 'Status Green',
    hex: '#4CAF50',
    text: 'text-status',
    bg: 'bg-status',
    bgSoft: 'bg-status/15',
    border: 'border-status',
    ring: 'ring-status'
  }
};

/** Map a status tone (incl. neutral) to text/border classes. */
export function toneClasses(tone: StatusTone): { text: string; border: string; bg: string } {
  if (tone === 'neutral') {
    return { text: 'text-lcars-muted', border: 'border-edge', bg: 'bg-edge/30' };
  }
  const d = DEPARTMENTS[tone];
  return { text: d.text, border: d.border, bg: d.bgSoft };
}
