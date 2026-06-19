import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { recoveryBrief } from '@/lib/mockData';
import { toneClasses } from '@/lib/departments';
import type { RecoveryPostureBand, StatusTone } from '@/lib/types';

export const metadata = { title: 'Recovery Brief · LCARS Portal' };

// ── Tone helpers ──────────────────────────────────────────────────────────────

const POSTURE_TONE: Record<RecoveryPostureBand, StatusTone> = {
  STRONG:  'status',
  STABLE:  'command',
  FRAGILE: 'operations',
  REST:    'medical',
  UNKNOWN: 'neutral'
};

// ── Section divider ───────────────────────────────────────────────────────────

function SectionRule({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="h-px flex-1 bg-edge/60" />
      <span className="shrink-0 text-[10px] font-bold uppercase tracking-[0.3em] text-lcars-muted">
        {label}
      </span>
      <div className="h-px flex-1 bg-edge/60" />
    </div>
  );
}

// ── Recovery Brief ────────────────────────────────────────────────────────────

export default function RecoveryBriefPage() {
  const brief = recoveryBrief;
  const postureTone = POSTURE_TONE[brief.posture];
  const pc = toneClasses(postureTone);

  // Format generated timestamp
  const generated = new Date(brief.generated).toLocaleTimeString('en-AU', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  });

  return (
    <div className="flex flex-col gap-4">

      {/* Header */}
      <LCARSPanel
        title="Recovery Brief"
        accent="medical"
        eyebrow={`Stardate ${brief.stardate} · Generated ${generated}`}
        actions={<StatusBadge label={brief.posture} tone={postureTone} />}
      >
        <p className="text-xs text-lcars-muted">
          The Recovery Brief leads with what the nervous system needs today.
          Mission detail follows when capacity supports it.
        </p>
      </LCARSPanel>

      {/* ── Recovery Posture ── */}
      <LCARSPanel title="Recovery Posture" accent="medical" eyebrow="What does my system need today?">
        <div className={`rounded-lcars border ${pc.border} ${pc.bg} p-5`}>
          <p className={`font-lcars text-3xl font-bold ${pc.text}`}>{brief.posture}</p>
          <p className="mt-2 text-sm text-lcars-text/90 leading-relaxed">{brief.posture_message}</p>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-lcars border border-edge bg-space/40 p-3">
            <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Sleep last night</p>
            <p className="mt-1 text-sm text-lcars-text/90">{brief.sleep_summary}</p>
          </div>
          <div className="rounded-lcars border border-edge bg-space/40 p-3">
            <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Nervous system</p>
            <p className="mt-1 text-sm text-lcars-text/90 capitalize">{brief.nervous_system}</p>
          </div>
          <div className="rounded-lcars border border-edge bg-space/40 p-3">
            <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Energy</p>
            <p className="mt-1 text-sm text-lcars-text/90">{brief.energy}</p>
          </div>
        </div>
      </LCARSPanel>

      {/* ── Capacity Today ── */}
      <LCARSPanel title="Capacity Today" accent="medical" eyebrow="What capacity is available?">
        <div className="rounded-lcars border border-command/40 bg-command/5 p-4">
          <p className="text-sm text-lcars-text/90 leading-relaxed">{brief.capacity_message}</p>
          <div className="mt-3 flex flex-wrap gap-4">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Best window</p>
              <p className="font-lcars text-lg font-semibold text-command">{brief.best_window}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Afternoon</p>
              <p className="text-sm text-lcars-text/90 mt-0.5">{brief.afternoon_note}</p>
            </div>
          </div>
        </div>
      </LCARSPanel>

      {/* ── Recovery Guidance ── */}
      <LCARSPanel
        title="Recovery Guidance"
        accent="medical"
        eyebrow="Medical Officer — standing orders today"
        actions={<StatusBadge label="Always present" tone="medical" />}
      >
        <ol className="flex flex-col gap-2">
          {brief.guidance.map((item, i) => (
            <li
              key={i}
              className="flex gap-3 rounded-lcars border border-edge bg-space/40 p-3 text-sm text-lcars-text/90 leading-relaxed"
            >
              <span className="font-lcars text-medical shrink-0 mt-0.5">{i + 1}.</span>
              {item}
            </li>
          ))}
        </ol>
      </LCARSPanel>

      {/* ── Today's Sustainable Load ── */}
      <LCARSPanel
        title="Today&apos;s Sustainable Load"
        accent="medical"
        eyebrow="What is a safe and sustainable mission load today?"
      >
        <div className="flex flex-col gap-2">
          <div className={`rounded-lcars border ${pc.border} ${pc.bg} px-4 py-3`}>
            <p className={`text-sm font-semibold ${pc.text}`}>{brief.load_summary}</p>
          </div>
          {[brief.active_mission_note, brief.new_starts_note, brief.decisions_note].map((note, i) => (
            <div key={i} className="flex gap-2 rounded-lcars border border-edge bg-space/40 px-4 py-3 text-sm text-lcars-text/90">
              <span className="text-lcars-muted shrink-0">·</span>
              {note}
            </div>
          ))}
        </div>
      </LCARSPanel>

      {/* ── Fleet (context) ── */}
      <LCARSPanel title="Fleet" accent="medical" eyebrow="Context — available when needed">
        <div className="rounded-lcars border border-edge bg-space/40 px-4 py-3">
          <p className="text-sm text-lcars-text/80">{brief.fleet_summary}</p>
        </div>
        <p className="mt-2 text-xs text-lcars-muted">
          Full mission detail, department status, and crew readiness are on the Captain&apos;s Chair.
          Fleet is context here — not the opening frame.
        </p>
      </LCARSPanel>

    </div>
  );
}
