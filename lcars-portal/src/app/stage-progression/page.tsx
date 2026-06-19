import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { stageProgressionRecord } from '@/lib/mockData';
import { toneClasses } from '@/lib/departments';
import type { StageAssessment, StageProgressionRecord } from '@/lib/types';

export const metadata = { title: 'Stage Progression · LCARS Portal' };

// ── Criteria met indicator ───────────────────────────────────────────────────

function CriterionMet({ met }: { met: boolean | 'partial' | 'unknown' }) {
  if (met === true)      return <span className="text-status text-sm">●</span>;
  if (met === 'partial') return <span className="text-command text-sm">◐</span>;
  return <span className="text-lcars-muted text-sm">○</span>;
}

// ── Stage description table ──────────────────────────────────────────────────

const STAGES = [
  {
    stage: 1,
    name: 'Stabilise',
    goal: 'Consistent daily recovery baseline',
    load: 'Minimal / protected',
    signal: 'Recovery posture stable across 14 of any 21 days; Medical Officer assessment'
  },
  {
    stage: 2,
    name: 'Restore Capacity',
    goal: 'Expand sustainable capacity',
    load: 'Moderate / earned',
    signal: '30-day posture pattern STABLE or STRONG majority; Life Participation trending up'
  },
  {
    stage: 3,
    name: 'Expand Mission',
    goal: 'Take on meaningful mission load',
    load: 'Active',
    signal: 'Capacity Index settled above BUILDING for 30 days; Captain\'s readiness assessment'
  },
  {
    stage: 4,
    name: 'Contribution & Legacy',
    goal: 'Full engagement with sustainable output',
    load: 'Full',
    signal: 'Stage 3 sustained without sustained posture decline'
  }
];

// ── Assessment outcome badge ─────────────────────────────────────────────────

const OUTCOME_LABEL: Record<StageAssessment['outcome'], string> = {
  monitoring:             'Monitoring',
  not_yet:               'Not yet',
  transition_recognised: 'Transition recognised'
};

const OUTCOME_TONE: Record<StageAssessment['outcome'], 'neutral' | 'command' | 'status'> = {
  monitoring:             'neutral',
  not_yet:               'command',
  transition_recognised: 'status'
};

// ── Components ───────────────────────────────────────────────────────────────

function StageMap({ current }: { current: 1 | 2 | 3 | 4 }) {
  return (
    <LCARSPanel title="Stage Map" accent="medical" eyebrow="Four stages — ROS-001 v1.1">
      <p className="mb-4 text-xs text-lcars-muted leading-relaxed">
        Transitions are recognised, not achieved. The Captain does not push toward them —
        consistent behaviour creates the conditions for them. A transition is offered by the
        Medical Officer when signals align; it is never triggered automatically.
      </p>
      <div className="flex flex-col gap-2">
        {STAGES.map((s) => {
          const isActive = s.stage === current;
          const isPast   = s.stage < current;
          const c = toneClasses(isActive ? 'medical' : isPast ? 'status' : 'neutral');
          return (
            <div
              key={s.stage}
              className={`rounded-lcars border p-4 ${
                isActive ? `${c.border} ${c.bg}` : 'border-edge bg-space/30'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span
                    className={`font-lcars text-2xl font-bold shrink-0 ${
                      isActive ? c.text : isPast ? 'text-status' : 'text-lcars-muted'
                    }`}
                  >
                    {s.stage}
                  </span>
                  <div>
                    <p className={`font-lcars text-sm font-semibold uppercase tracking-wider ${
                      isActive ? c.text : isPast ? 'text-status' : 'text-lcars-muted'
                    }`}>
                      {s.name}
                    </p>
                    <p className="text-xs text-lcars-text/70 mt-0.5">{s.goal}</p>
                  </div>
                </div>
                {isActive && <StatusBadge label="Current" tone="medical" />}
                {isPast   && <StatusBadge label="Complete" tone="status" />}
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 text-xs text-lcars-muted">
                <div>
                  <span className="uppercase tracking-wider text-[10px]">Mission load · </span>
                  {s.load}
                </div>
                <div>
                  <span className="uppercase tracking-wider text-[10px]">Transition signal · </span>
                  {s.signal}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </LCARSPanel>
  );
}

function Stage2Criteria({ record }: { record: StageProgressionRecord }) {
  const { stable_or_strong, total_recorded, threshold, period } = record.stability_signal;

  return (
    <LCARSPanel
      title="Stage 2 Recognition Criteria"
      accent="medical"
      eyebrow="What the system is watching for"
    >
      <p className="mb-4 text-xs text-lcars-muted leading-relaxed">
        These criteria are observed, not pursued. When they align, the Medical Officer will
        initiate a transition assessment. No single criterion triggers a transition automatically.
      </p>

      {/* Stability signal bar */}
      <div className="mb-4 rounded-lcars border border-edge bg-space/40 p-4">
        <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-2">
          Stability signal — {period}
        </p>
        <div className="flex items-center gap-3">
          <div className="flex-1 h-3 rounded-full bg-edge/40 overflow-hidden">
            <div
              className="h-full rounded-full bg-command transition-all"
              style={{ width: `${Math.min((stable_or_strong / threshold) * 100, 100)}%` }}
            />
          </div>
          <span className="font-lcars text-sm font-bold text-command shrink-0">
            {stable_or_strong} / {threshold}
          </span>
        </div>
        <p className="text-xs text-lcars-muted mt-1">
          {stable_or_strong} day{stable_or_strong !== 1 ? 's' : ''} STABLE or STRONG
          of {threshold} needed ({total_recorded} days recorded)
        </p>
      </div>

      {/* Criteria checklist */}
      <div className="flex flex-col gap-3">
        {record.stage2_criteria.map((criterion, i) => (
          <div key={i} className="flex gap-3 rounded-lcars border border-edge bg-space/30 p-3">
            <CriterionMet met={criterion.met} />
            <div>
              <p className="text-sm font-semibold text-lcars-text">{criterion.label}</p>
              <p className="text-xs text-lcars-muted mt-0.5 leading-relaxed">{criterion.detail}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex gap-4 text-[10px] text-lcars-muted">
        <span className="flex items-center gap-1.5"><span className="text-status">●</span> Met</span>
        <span className="flex items-center gap-1.5"><span className="text-command">◐</span> Partial</span>
        <span className="flex items-center gap-1.5"><span className="text-lcars-muted">○</span> Not yet / unknown</span>
      </div>
    </LCARSPanel>
  );
}

function AssessmentLog({ assessments }: { assessments: StageAssessment[] }) {
  return (
    <LCARSPanel
      title="Assessment Log"
      accent="medical"
      eyebrow="Knowledge Officer governance record"
    >
      <p className="mb-4 text-xs text-lcars-muted leading-relaxed">
        Formal assessments are recorded here by the Knowledge Officer and Medical Officer.
        This is a governance record — not a performance log.
      </p>
      {assessments.length === 0 ? (
        <p className="text-sm text-lcars-muted italic">No assessments recorded yet.</p>
      ) : (
        <div className="flex flex-col gap-4">
          {assessments.map((a, i) => (
            <div key={i} className="rounded-lcars border border-edge bg-space/30 p-4">
              <div className="flex items-start justify-between gap-3 mb-2">
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-lcars-muted">{a.date}</p>
                  <p className="text-sm font-semibold text-lcars-text mt-0.5">{a.signal}</p>
                  <p className="text-[10px] text-lcars-muted mt-0.5">Author: {a.author}</p>
                </div>
                <StatusBadge label={OUTCOME_LABEL[a.outcome]} tone={OUTCOME_TONE[a.outcome]} />
              </div>
              <p className="text-xs text-lcars-text/80 leading-relaxed border-t border-edge/60 pt-2 mt-2">
                {a.notes}
              </p>
            </div>
          ))}
        </div>
      )}
    </LCARSPanel>
  );
}

function StandingNote() {
  return (
    <LCARSPanel title="Standing Note" accent="medical" eyebrow="ROS-001 v1.1 — Stage protocol">
      <div className="rounded-lcars border border-medical/30 bg-medical/5 p-4 text-sm text-lcars-text/90 leading-relaxed space-y-2">
        <p>
          The goal of Stage 1 is not to accumulate a high Recovery Score. The goal is to behave
          consistently in ways that allow the nervous system to settle.
        </p>
        <p>
          A stable nervous system produces rising scores as a downstream effect — not as a target.
        </p>
        <p>
          The Captain does not advance stages. The Medical Officer and Knowledge Officer recognise
          when the conditions for transition have emerged, and offer the assessment. The Captain
          reflects and decides.
        </p>
        <p className="text-lcars-muted text-xs border-t border-edge/60 pt-2 mt-2">
          Standing Tone Instruction — ROS-001 v1.1: The Captain is not broken. Recovery is not
          repair. The nervous system is doing its job. The conditions around it need to change,
          not the Captain.
        </p>
      </div>
    </LCARSPanel>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function StageProgressionPage() {
  const record = stageProgressionRecord;

  return (
    <div className="flex flex-col gap-4">

      {/* Stage Map */}
      <StageMap current={record.current_stage} />

      {/* Stage 2 Criteria */}
      <Stage2Criteria record={record} />

      {/* Assessment Log */}
      <AssessmentLog assessments={record.assessments} />

      {/* Standing Note */}
      <StandingNote />

    </div>
  );
}
