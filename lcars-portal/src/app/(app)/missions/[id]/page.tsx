'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { missions as mockMissions } from '@/lib/mockData';
import type { Mission } from '@/lib/types';

// Canonical Supabase status values (CHECK constraint on missions.status)
const STATUS_OPTIONS = [
  'Idea', 'Designed', 'Approved for Engineering', 'Implemented', 'Tested',
  'Awaiting Number One Review', 'Validated', 'Awaiting XO Approval',
  'Awaiting Captain Approval', 'Approved',
  'Blocked', 'Requires Rework', 'Closed', 'Archived',
];

function fmt(iso?: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function Field({ label, value, mono }: { label: string; value?: string | null; mono?: boolean }) {
  if (!value) return null;
  return (
    <div className="flex flex-col gap-0.5">
      <p className="text-[9px] uppercase tracking-[0.2em] text-lcars-muted">{label}</p>
      <p className={`text-sm text-lcars-text break-all ${mono ? 'font-mono text-xs' : ''}`}>{value}</p>
    </div>
  );
}

export default function MissionDetailPage() {
  const { id } = useParams<{ id: string }>();

  const [mission, setMission] = useState<Mission | null>(null);
  const [newStatus, setNewStatus] = useState('');
  const [note, setNote]           = useState('');
  const [saving, setSaving]       = useState(false);
  const [saved, setSaved]         = useState(false);
  const [error, setError]         = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      const supabase = createSupabaseBrowserClient();
      const { data } = await supabase
        .from('missions')
        .select('*')
        .eq('mission_id', id)
        .single();

      if (data) {
        setMission(data as Mission);
        setNewStatus(data.status);
      } else {
        const mock = mockMissions.find((m) => m.mission_id === id) ?? null;
        setMission(mock);
        if (mock) setNewStatus(mock.status);
      }
    }
    load();
  }, [id]);

  async function handleSave() {
    if (!mission) return;
    setSaving(true);
    setError(null);

    const supabase = createSupabaseBrowserClient();
    const payload: Record<string, unknown> = { status: newStatus };
    if (note.trim()) payload.notes = note.trim();

    const { error: dbError } = await supabase
      .from('missions')
      .update(payload)
      .eq('mission_id', mission.mission_id);

    setSaving(false);
    if (dbError) {
      setError(dbError.message);
    } else {
      setSaved(true);
      setMission({ ...mission, status: newStatus });
      setNote('');
      setTimeout(() => setSaved(false), 2000);
    }
  }

  if (!mission) {
    return <div className="py-16 text-center text-lcars-muted text-sm">Loading mission…</div>;
  }

  const eyebrow = [mission.mission_type, mission.task_type].filter(Boolean).join(' · ') || 'Mission';

  return (
    <div className="flex flex-col gap-4">

      <Link href="/missions" className="self-start text-[10px] uppercase tracking-[0.25em] text-lcars-muted hover:text-command">
        ← Mission Registry
      </Link>

      {/* Header */}
      <LCARSPanel title={mission.mission_id} accent="command" eyebrow={eyebrow} actions={<StatusBadge label={mission.status} status={mission.status} />}>
        <h2 className="font-lcars text-xl font-bold text-lcars-text">{mission.title}</h2>
        {mission.description && (
          <p className="mt-2 text-sm text-lcars-muted leading-relaxed">{mission.description}</p>
        )}
        <div className="mt-3 flex flex-wrap gap-3">
          {mission.priority && (
            <span className="rounded border border-edge px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-command">
              {mission.priority}
            </span>
          )}
          {mission.created_by && (
            <span className="text-xs text-lcars-muted">Created by <span className="text-lcars-text">{mission.created_by}</span></span>
          )}
        </div>
      </LCARSPanel>

      {/* Details grid */}
      <LCARSPanel title="Mission Details" accent="science" eyebrow="Operational record">
        <div className="grid grid-cols-2 gap-x-6 gap-y-4">
          <Field label="Mission ID"   value={mission.mission_id} />
          <Field label="Status"       value={mission.status} />
          <Field label="Mission Type" value={mission.mission_type} />
          <Field label="Task Type"    value={mission.task_type} />
          <Field label="Priority"     value={mission.priority} />
          <Field label="Created"      value={fmt(mission.created_at)} />
          <Field label="Last Updated" value={fmt(mission.updated_at)} />
          <Field label="Closed"       value={fmt(mission.closed_at)} />
          {mission.outcome_rating != null && (
            <Field label="Outcome Rating" value={String(mission.outcome_rating)} />
          )}
          {mission.rework_of && (
            <Field label="Rework Of" value={mission.rework_of} />
          )}
        </div>
      </LCARSPanel>

      {/* Engineering */}
      {(mission.repo || mission.branch_name || mission.pr_url) && (
        <LCARSPanel title="Engineering" accent="engineering" eyebrow="Repository & delivery">
          <div className="flex flex-col gap-3">
            <Field label="Repository"   value={mission.repo} mono />
            <Field label="Branch"       value={mission.branch_name} mono />
            {mission.pr_url && (
              <div className="flex flex-col gap-0.5">
                <p className="text-[9px] uppercase tracking-[0.2em] text-lcars-muted">Pull Request</p>
                <a
                  href={mission.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs font-mono text-science hover:underline break-all"
                >
                  {mission.pr_url}
                </a>
              </div>
            )}
          </div>
        </LCARSPanel>
      )}

      {/* Status update */}
      <LCARSPanel title="Update Status" accent="command" eyebrow="Write-back to mission registry">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">New status</p>
            <div className="flex flex-wrap gap-2">
              {STATUS_OPTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => setNewStatus(s)}
                  className={`rounded-lcars border px-3 py-1.5 text-xs font-semibold transition-colors ${
                    newStatus === s
                      ? 'border-command bg-command/20 text-command'
                      : 'border-edge bg-space/40 text-lcars-muted hover:border-command/50'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">Note (optional)</p>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder="What changed? What's the blocker?"
              className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none resize-none"
            />
          </div>

          {error && <p className="text-xs text-operations">{error}</p>}

          <button
            onClick={handleSave}
            disabled={saving || (newStatus === mission.status && !note)}
            className="w-full rounded-lcars bg-command px-4 py-2.5 font-lcars text-sm font-bold uppercase tracking-[0.2em] text-space transition-opacity hover:opacity-80 disabled:opacity-40"
          >
            {saving ? 'Saving…' : saved ? '✓ Saved' : 'Update Mission'}
          </button>
        </div>
      </LCARSPanel>

    </div>
  );
}
