'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { LCARSPanel } from '@/components/LCARSPanel';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

type RAGStatus = 'Green' | 'Amber' | 'Red';
type CapacityRating = 'Green' | 'Amber' | 'Red';

function RAGField({
  label, value, onChange
}: {
  label: string;
  value: RAGStatus | '';
  onChange: (v: RAGStatus) => void;
}) {
  const options: { value: RAGStatus; cls: string }[] = [
    { value: 'Green', cls: 'border-status bg-status/20 text-status' },
    { value: 'Amber', cls: 'border-command bg-command/20 text-command' },
    { value: 'Red',   cls: 'border-operations bg-operations/20 text-operations' },
  ];
  return (
    <div className="flex flex-col gap-1">
      <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">{label}</p>
      <div className="flex gap-2">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`flex-1 rounded-lcars border py-1.5 text-xs font-bold transition-colors ${
              value === opt.value ? opt.cls : 'border-edge bg-space/40 text-lcars-muted hover:border-edge/80'
            }`}
          >
            {opt.value}
          </button>
        ))}
      </div>
    </div>
  );
}

function TextArea({
  label, value, onChange, placeholder, rows = 2
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  rows?: number;
}) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">{label}</p>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        placeholder={placeholder}
        className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none resize-none"
      />
    </div>
  );
}

export default function CaptainsLogPage() {
  const router = useRouter();
  const today = new Date().toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' });

  const [healthStatus, setHealthStatus]       = useState<RAGStatus | ''>('');
  const [workStatus, setWorkStatus]           = useState<RAGStatus | ''>('');
  const [personalStatus, setPersonalStatus]   = useState<RAGStatus | ''>('');
  const [capacityRating, setCapacityRating]   = useState<CapacityRating | ''>('');
  const [whatHappened, setWhatHappened]       = useState('');
  const [whatChanged, setWhatChanged]         = useState('');
  const [wins, setWins]                       = useState('');
  const [blockers, setBlockers]               = useState('');
  const [decisionsMade, setDecisionsMade]     = useState('');
  const [tomorrowPriority, setTomorrowPriority] = useState('');
  const [overallNote, setOverallNote]         = useState('');

  const [saving, setSaving] = useState(false);
  const [saved, setSaved]   = useState(false);
  const [error, setError]   = useState<string | null>(null);

  async function handleSubmit() {
    setSaving(true);
    setError(null);

    const payload: Record<string, unknown> = {
      log_date: new Date().toISOString().slice(0, 10),
      source:   'ui',
    };

    if (healthStatus)      payload.health_status        = healthStatus;
    if (workStatus)        payload.work_status          = workStatus;
    if (personalStatus)    payload.personal_status      = personalStatus;
    if (capacityRating)    payload.captain_capacity_rating = capacityRating;
    if (whatHappened)      payload.what_happened        = whatHappened;
    if (whatChanged)       payload.what_changed         = whatChanged;
    if (wins)              payload.wins                 = wins;
    if (blockers)          payload.blockers             = blockers;
    if (decisionsMade)     payload.decisions_made       = decisionsMade;
    if (tomorrowPriority)  payload.tomorrows_priority   = tomorrowPriority;
    if (overallNote)       payload.overall_note         = overallNote;

    const supabase = createSupabaseBrowserClient();
    const { error: dbError } = await supabase
      .from('captains_log_entries')
      .upsert(payload, { onConflict: 'log_date' });

    setSaving(false);
    if (dbError) {
      setError(dbError.message);
    } else {
      setSaved(true);
      setTimeout(() => router.push('/captains-chair'), 1500);
    }
  }

  if (saved) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-16">
        <div className="flex h-14 w-14 items-center justify-center rounded-full border border-status bg-status/10">
          <span className="font-lcars text-2xl text-status">✓</span>
        </div>
        <p className="font-lcars text-lg font-bold text-status">Log entry saved</p>
        <p className="text-sm text-lcars-muted">Returning to Captain&apos;s Chair…</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Captain's Log"
        accent="command"
        eyebrow={today}
      >
        <p className="text-xs text-lcars-muted">
          End-of-day structured reflection. Upserts on date — re-submitting today updates the record.
        </p>
      </LCARSPanel>

      {/* RAG status */}
      <LCARSPanel title="Status" accent="command" eyebrow="Today's RAG ratings">
        <div className="flex flex-col gap-4">
          <RAGField label="Health" value={healthStatus} onChange={setHealthStatus} />
          <RAGField label="Work" value={workStatus} onChange={setWorkStatus} />
          <RAGField label="Personal" value={personalStatus} onChange={setPersonalStatus} />
          <RAGField label="Captain capacity" value={capacityRating} onChange={setCapacityRating} />
        </div>
      </LCARSPanel>

      {/* Narrative */}
      <LCARSPanel title="Log Entry" accent="command" eyebrow="Narrative fields — all optional">
        <div className="flex flex-col gap-4">
          <TextArea
            label="What happened today"
            value={whatHappened}
            onChange={setWhatHappened}
            placeholder="Key events, meetings, outputs."
            rows={3}
          />
          <TextArea
            label="What changed"
            value={whatChanged}
            onChange={setWhatChanged}
            placeholder="Shifts in situation, understanding, or direction."
          />
          <TextArea
            label="Wins"
            value={wins}
            onChange={setWins}
            placeholder="Progress made. Things that worked."
          />
          <TextArea
            label="Blockers"
            value={blockers}
            onChange={setBlockers}
            placeholder="What's in the way."
          />
          <TextArea
            label="Decisions made"
            value={decisionsMade}
            onChange={setDecisionsMade}
            placeholder="Decisions taken today."
          />
          <TextArea
            label="Tomorrow's priority"
            value={tomorrowPriority}
            onChange={setTomorrowPriority}
            placeholder="The one thing that matters most tomorrow."
          />
          <TextArea
            label="Overall note"
            value={overallNote}
            onChange={setOverallNote}
            placeholder="Anything else for the record."
          />
        </div>
      </LCARSPanel>

      {error && (
        <p className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations">
          {error}
        </p>
      )}

      <button
        onClick={handleSubmit}
        disabled={saving}
        className="w-full rounded-lcars bg-command px-4 py-3 font-lcars text-sm font-bold uppercase tracking-[0.2em] text-space transition-opacity hover:opacity-80 disabled:opacity-40"
      >
        {saving ? 'Saving…' : 'Save Log Entry'}
      </button>
    </div>
  );
}
