'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { missions as mockMissions } from '@/lib/mockData';
import { DEPARTMENTS } from '@/lib/departments';
import type { Mission } from '@/lib/types';

const STATUS_OPTIONS = [
  'ASSIGNED', 'IN_PROGRESS', 'REVIEW', 'ACTIVE', 'BLOCKED', 'COMPLETE', 'DEFERRED'
];

export default function MissionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [mission, setMission] = useState<Mission | null>(null);
  const [newStatus, setNewStatus] = useState('');
  const [note, setNote]           = useState('');
  const [saving, setSaving]       = useState(false);
  const [saved, setSaved]         = useState(false);
  const [error, setError]         = useState<string | null>(null);

  useEffect(() => {
    // Try live Supabase first, fall back to mock
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
    const updatePayload: Record<string, unknown> = { status: newStatus };
    if (note.trim()) updatePayload.notes = note.trim();

    const { error: dbError } = await supabase
      .from('missions')
      .update(updatePayload)
      .eq('mission_id', mission.mission_id);

    setSaving(false);
    if (dbError) {
      setError(dbError.message);
    } else {
      setSaved(true);
      setMission({ ...mission, status: newStatus });
      setTimeout(() => setSaved(false), 2000);
    }
  }

  if (!mission) {
    return (
      <div className="py-16 text-center text-lcars-muted text-sm">
        Loading mission…
      </div>
    );
  }

  const dept = mission.department ? DEPARTMENTS[mission.department] : undefined;

  return (
    <div className="flex flex-col gap-4">

      {/* Back */}
      <Link
        href="/missions"
        className="self-start text-[10px] uppercase tracking-[0.25em] text-lcars-muted hover:text-command"
      >
        ← Mission Registry
      </Link>

      {/* Header */}
      <LCARSPanel
        title={mission.mission_id}
        accent="command"
        eyebrow={`${dept?.label ?? mission.department} · ${mission.reference}`}
        actions={<StatusBadge label={mission.status} status={mission.status} />}
      >
        <h2 className="font-lcars text-xl font-bold text-lcars-text">{mission.title}</h2>
        <div className="mt-2 flex flex-wrap gap-4 text-xs text-lcars-muted">
          <span>Owner: <span className="text-lcars-text">{mission.owner}</span></span>
          <span>Specialist: <span className="text-lcars-text">{mission.specialist}</span></span>
          <span>Priority: <span className="text-lcars-text font-bold">{mission.priority}</span></span>
        </div>
      </LCARSPanel>

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

          {error && (
            <p className="text-xs text-operations">{error}</p>
          )}

          <button
            onClick={handleSave}
            disabled={saving || newStatus === mission.status && !note}
            className="w-full rounded-lcars bg-command px-4 py-2.5 font-lcars text-sm font-bold uppercase tracking-[0.2em] text-space transition-opacity hover:opacity-80 disabled:opacity-40"
          >
            {saving ? 'Saving…' : saved ? '✓ Saved' : 'Update Mission'}
          </button>
        </div>
      </LCARSPanel>

    </div>
  );
}
