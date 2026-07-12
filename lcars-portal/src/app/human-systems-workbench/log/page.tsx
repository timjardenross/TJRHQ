'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Shell } from '@/app/human-systems-workbench/_components/Shell';
import { Card, Button, Textarea } from '@/components/ui';
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
    { value: 'Green', cls: 'bg-wb-ok/15 text-wb-ok-on border border-wb-ok' },
    { value: 'Amber', cls: 'bg-wb-warn/15 text-wb-warn-on border border-wb-warn' },
    { value: 'Red',   cls: 'bg-wb-crit/15 text-wb-crit-on border border-wb-crit' },
  ];
  return (
    <div className="flex flex-col gap-1">
      <p className="text-[11px] uppercase tracking-[0.12em] text-wb-ink2">{label}</p>
      <div className="flex gap-2">
        {options.map((opt) => {
          const selected = value === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(opt.value)}
              className={`flex-1 rounded-md py-1.5 text-xs font-semibold transition-colors ${
                selected ? opt.cls : 'border border-wb-line bg-wb-surface text-wb-ink2 hover:bg-wb-line'
              }`}
            >
              {opt.value}
            </button>
          );
        })}
      </div>
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
      setTimeout(() => router.push('/human-systems-workbench?domain=recovery'), 1500);
    }
  }

  if (saved) {
    return (
      <Shell
        title="Captain's Log"
        eyebrow="Recovery & Capacity"
        back={{ href: '/human-systems-workbench?domain=recovery', label: 'Recovery' }}
      >
        <div className="flex flex-col items-center justify-center gap-4 py-16">
          <div className="flex h-14 w-14 items-center justify-center rounded-full border border-wb-ok bg-wb-ok/15">
            <span className="text-2xl text-wb-ok-on" aria-hidden="true">✓</span>
          </div>
          <p className="font-serif text-lg text-wb-ink">Log entry saved</p>
          <p className="text-sm text-wb-ink2">Returning to Recovery…</p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell
      title="Captain's Log"
      eyebrow="Recovery & Capacity"
      back={{ href: '/human-systems-workbench?domain=recovery', label: 'Recovery' }}
    >
      <div className="flex flex-col gap-4">
        <Card title="Captain's Log">
          <p className="text-[11px] uppercase tracking-[0.12em] text-wb-ink2">{today}</p>
          <p className="mt-2 text-[14px] leading-relaxed text-wb-ink2">
            End-of-day structured reflection. Close the recovery loop — log what was, what changed,
            and what tomorrow needs. Upserts on date — re-submitting today updates the record.
          </p>
        </Card>

        {/* D-055 — Recovery reflection first */}
        <Card title="Recovery Reflection">
          <p className="text-[11px] uppercase tracking-[0.12em] text-wb-ink2">
            D-055 · Capacity loop — complete before mission log
          </p>
          <p className="mb-4 mt-2 text-[14px] leading-relaxed text-wb-ink2">
            Before logging missions, close the recovery loop. How did the day land in the body?
            This is the primary record — mission detail is context.
          </p>
          <div className="flex flex-col gap-4">
            <Textarea
              label="Recovery note — how did the day land?"
              value={overallNote}
              onChange={(e) => setOverallNote(e.target.value)}
              rows={3}
              placeholder="How did the nervous system land today? What restored or depleted capacity? What does the body need tonight?"
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <RAGField label="Health" value={healthStatus} onChange={setHealthStatus} />
              <RAGField label="Captain capacity" value={capacityRating} onChange={setCapacityRating} />
            </div>
          </div>
        </Card>

        {/* RAG status */}
        <Card title="Status">
          <p className="mb-4 text-[11px] uppercase tracking-[0.12em] text-wb-ink2">Work and personal RAG</p>
          <div className="flex flex-col gap-4">
            <RAGField label="Work" value={workStatus} onChange={setWorkStatus} />
            <RAGField label="Personal" value={personalStatus} onChange={setPersonalStatus} />
          </div>
        </Card>

        {/* Narrative */}
        <Card title="Mission Log">
          <p className="mb-4 text-[11px] uppercase tracking-[0.12em] text-wb-ink2">Narrative fields — all optional</p>
          <div className="flex flex-col gap-4">
            <Textarea
              label="What happened today"
              value={whatHappened}
              onChange={(e) => setWhatHappened(e.target.value)}
              rows={3}
              placeholder="Key events, meetings, outputs."
            />
            <Textarea
              label="What changed"
              value={whatChanged}
              onChange={(e) => setWhatChanged(e.target.value)}
              rows={2}
              placeholder="Shifts in situation, understanding, or direction."
            />
            <Textarea
              label="Wins"
              value={wins}
              onChange={(e) => setWins(e.target.value)}
              rows={2}
              placeholder="Progress made. Things that worked."
            />
            <Textarea
              label="Blockers"
              value={blockers}
              onChange={(e) => setBlockers(e.target.value)}
              rows={2}
              placeholder="What's in the way."
            />
            <Textarea
              label="Decisions made"
              value={decisionsMade}
              onChange={(e) => setDecisionsMade(e.target.value)}
              rows={2}
              placeholder="Decisions taken today."
            />
            <Textarea
              label="Tomorrow's priority"
              value={tomorrowPriority}
              onChange={(e) => setTomorrowPriority(e.target.value)}
              rows={2}
              placeholder="The one thing that matters most tomorrow — through a capacity lens."
            />
          </div>
        </Card>

        {error && (
          <p className="rounded-md border border-wb-crit bg-wb-crit/15 px-4 py-3 text-sm text-wb-crit-on">
            {error}
          </p>
        )}

        <Button
          variant="primary"
          onClick={handleSubmit}
          disabled={saving}
          className="w-full"
        >
          {saving ? 'Saving…' : 'Save Log Entry'}
        </Button>
      </div>
    </Shell>
  );
}
