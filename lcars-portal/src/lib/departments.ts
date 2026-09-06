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

/** Map a status tone (incl. neutral) to text/border/dot classes.
 *
 * Real-Captain-walkthrough revision (2026-07-10): every department tone
 * (command/engineering/operations/medical/science/status) now renders the
 * same single brand accent rather than five decorative colours - StatusBadge
 * and every other caller of toneClasses() across Missions/Comms/Advisory
 * Council/etc. gets this fix in one place. Genuinely semantic status
 * (ok/warn/crit/unknown) is a completely separate system - stateToneClasses()
 * below - and is deliberately untouched by this change. */
export function toneClasses(tone: StatusTone): { text: string; border: string; bg: string; dot: string } {
  if (tone === 'neutral') {
    return { text: 'text-lcars-chrome-muted', border: 'border-lcars-chrome-border', bg: 'bg-lcars-chrome-border-soft', dot: 'bg-lcars-chrome-muted' };
  }
  return { text: 'text-lcars-chrome-accent', border: 'border-lcars-chrome-accent/30', bg: 'bg-lcars-chrome-accent/10', dot: 'bg-lcars-chrome-accent' };
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
  info:    { text: 'text-state-info',    border: 'border-state-info',    bg: 'bg-state-info/15',    dot: 'bg-state-info',    on: 'text-state-info-on' },
};

/** Map a state tone to text/border/bg/dot classes, plus a high-contrast `on` variant for text on solid fills. */
export function stateToneClasses(tone: StateTone): { text: string; border: string; bg: string; dot: string; on: string } {
  return STATE_CLASSES[tone];
}

// ── Severity-vocabulary adapters (2026-08-29, Severity-Vocab-
// Canonicalization-Plan) ─────────────────────────────────────────────────
// Every bespoke severity/status union in the app collapses onto StateTone
// through one of these small adapters instead of hand-rolling its own
// color classes. Add a new adapter here — never a new bespoke vocabulary
// elsewhere — the next time a page needs to color a status-like string.

/** self-improvement-findings' Finding.severity and Decision.decision. */
export function severityToTone(severity: 'info' | 'low' | 'medium' | 'high' | 'critical'): StateTone {
  switch (severity) {
    case 'info': return 'info';
    case 'low': return 'ok';
    case 'medium': return 'warn';
    case 'high': return 'warn';
    case 'critical': return 'crit';
  }
}

/** self-improvement-findings' Decision.decision. */
export function decisionToTone(decision: 'approved' | 'rejected' | 'more_evidence'): StateTone {
  switch (decision) {
    case 'approved': return 'ok';
    case 'rejected': return 'crit';
    case 'more_evidence': return 'warn';
  }
}

/** HQ Evolution's Opportunity.lifecycle_state (self-improvement-findings). */
export function lifecycleStateToTone(state: string): StateTone {
  switch (state) {
    case 'proposed': return 'warn';       // needs a human decision
    case 'approved': return 'ok';
    case 'implementing': return 'info';
    case 'verifying': return 'info';
    case 'learned': return 'ok';
    case 'watching': return 'info';
    case 'rejected': return 'unknown';
    case 'investigating': return 'info';
    case 'resolved_before_research': return 'unknown';
    case 'discovered':
    default: return 'unknown';
  }
}

/** HQ Evolution's Opportunity.value ('low'|'medium'|'high'|null). */
export function valueToTone(value: string | null | undefined): StateTone {
  switch (value) {
    case 'high': return 'ok';
    case 'medium': return 'warn';
    case 'low': return 'unknown';
    default: return 'unknown';
  }
}

/** HQ Evolution's Opportunity.risk_level, set by PolicyEngine (not the model). */
export function opportunityRiskToTone(risk: string | null | undefined): StateTone {
  switch (risk) {
    case 'critical': return 'crit';
    case 'high': return 'warn';
    case 'medium': return 'warn';
    case 'low': return 'ok';
    default: return 'unknown';
  }
}

/** HQ Evolution V2's Opportunity.outcome.outcome_result. */
export function outcomeResultToTone(result: string | null | undefined): StateTone {
  switch (result) {
    case 'improved': return 'ok';
    case 'no_material_change': return 'unknown';
    case 'regressed': return 'crit';
    case 'inconclusive': return 'warn';
    case 'not_yet_ready': return 'info';
    default: return 'unknown';
  }
}

/** alerts.ts's AlertSeverity ('critical'|'high'|'warning'). */
export function alertSeverityToTone(severity: 'critical' | 'high' | 'warning'): StateTone {
  switch (severity) {
    case 'critical': return 'crit';
    case 'high': return 'warn';
    case 'warning': return 'warn';
  }
}

/** intelligenceRisk.ts's RiskLevel ('HIGH'|'MEDIUM'|'LOW'|''). Business-logic
 *  string, not just display — verify no exact-case dependents before
 *  reusing this for anything beyond color. */
export function riskLevelToTone(level: 'HIGH' | 'MEDIUM' | 'LOW' | ''): StateTone {
  switch (level) {
    case 'HIGH': return 'crit';
    case 'MEDIUM': return 'warn';
    case 'LOW': return 'ok';
    default: return 'unknown';
  }
}

/** delivery.ts's Bottleneck.severity ('critical'|'high'|'medium'|'low'). */
export function deliverySeverityToTone(severity: 'critical' | 'high' | 'medium' | 'low'): StateTone {
  switch (severity) {
    case 'critical': return 'crit';
    case 'high': return 'warn';
    case 'medium': return 'warn';
    case 'low': return 'ok';
  }
}

/** emergency-alert-hub-workbench's AU alert tiers. Accepts a plain string
 *  since the API's EmergencyAlertEntry.severity field is untyped. */
export function emergencyAlertTierToTone(tier: string): StateTone {
  switch (tier) {
    case 'emergency_warning': return 'crit';
    case 'watch_and_act': return 'warn';
    case 'advice': return 'ok';
    default: return 'unknown';
  }
}

/** capacity_checkins.capacity_state ('green'|'orange'|'red'). THE primary
 *  capacity indicator — see human-systems-workbench/_components/types.ts's
 *  capacityStateStatus, which now calls this. */
export function capacityStateToTone(state: string | null): StateTone {
  switch (state) {
    case 'green': return 'ok';
    case 'orange': return 'warn';
    case 'red': return 'crit';
    default: return 'unknown';
  }
}

/** health_signals.severity ('critical'|'severe'|...) as used for the
 *  Captain's Chair situation-strip badges. */
export function healthSeverityToTone(severity: string): StateTone {
  switch (severity) {
    case 'critical': return 'crit';
    case 'severe': return 'warn';
    default: return 'unknown';
  }
}

/** Map common mission/service status strings to a department tone. Shared by
 *  StatusBadge (legacy) and WorkbenchBadge (wb-* system) so both render off
 *  one inference rule instead of forking it. */
export function inferTone(status: string): StatusTone {
  const s = status.toUpperCase();
  if (s.includes('BLOCK') || s.includes('OFFLINE') || s.includes('CRITICAL'))
    return 'operations';
  if (s.includes('REVIEW') || s.includes('DEGRADED') || s.includes('PENDING'))
    return 'command';
  if (
    s.includes('COMPLET') ||
    s.includes('OPERATIONAL') ||
    s.includes('GREEN') ||
    s.includes('DONE') ||
    s.includes('ON DUTY')
  )
    return 'status';
  if (s.includes('PROGRESS') || s.includes('ACTIVE') || s.includes('ASSIGNED'))
    return 'medical';
  return 'neutral';
}
