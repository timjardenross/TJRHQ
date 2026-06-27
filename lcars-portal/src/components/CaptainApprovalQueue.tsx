'use client';

// MSN-0176: Captain's Chair — live approval queue for missions awaiting decision.
// Calls POST /api/missions/{id}/approve and /reject from the browser.

import { useCallback, useEffect, useState } from 'react';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

interface QueueMission {
  mission_id: string;
  title: string;
  status: string;
  priority: string | null;
  created_by: string | null;
  created_at: string | null;
}

const AWAITING_STATUSES = ['Awaiting Captain Approval', 'Awaiting XO Approval'];

function shortId(missionId: string): string {
  const m = missionId.match(/(\d+)$/);
  return m ? m[1] : missionId;
}

export function CaptainApprovalQueue() {
  const [missions, setMissions] = useState<QueueMission[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<string | null>(null);
  const [rejectReasonFor, setRejectReasonFor] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [flash, setFlash] = useState<{ id: string; msg: string; ok: boolean } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const supabase = createSupabaseBrowserClient();
      const { data } = await supabase
        .from('missions')
        .select('mission_id, title, status, priority, created_by, created_at')
        .in('status', AWAITING_STATUSES)
        .order('created_at', { ascending: false })
        .limit(20);
      setMissions(data ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const decide = useCallback(async (missionId: string, decision: 'approve' | 'reject', reason?: string) => {
    setActing(missionId);
    try {
      const resp = await fetch(`/api/missions/${encodeURIComponent(missionId)}/${decision}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'LCARS', owner: 'Captain', ...(reason ? { reason } : {}) }),
      });
      const data = await resp.json();
      if (resp.ok) {
        setFlash({ id: missionId, msg: decision === 'approve' ? 'Approved' : 'Requires Rework', ok: true });
        setMissions(prev => prev.filter(m => m.mission_id !== missionId));
      } else {
        setFlash({ id: missionId, msg: data.error ?? 'Failed', ok: false });
      }
    } catch (e) {
      setFlash({ id: missionId, msg: String(e), ok: false });
    } finally {
      setActing(null);
      setRejectReasonFor(null);
      setRejectReason('');
      setTimeout(() => setFlash(null), 4000);
    }
  }, []);

  if (loading) {
    return (
      <div className="rounded-lcars border border-edge bg-panel/60 p-3">
        <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted mb-3">Captain&apos;s Queue</p>
        <p className="text-xs text-lcars-muted animate-pulse">Loading…</p>
      </div>
    );
  }

  if (missions.length === 0) {
    return (
      <div className="rounded-lcars border border-edge bg-panel/60 p-3">
        <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted mb-3">Captain&apos;s Queue</p>
        <p className="text-xs text-lcars-muted">No missions awaiting approval.</p>
      </div>
    );
  }

  return (
    <div className="rounded-lcars border border-command/40 bg-command/5 p-3">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-[0.25em] text-command">
          Captain&apos;s Queue — {missions.length} awaiting decision
        </p>
        <button
          onClick={load}
          className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:text-command transition-colors"
        >
          Refresh
        </button>
      </div>

      {flash && (
        <div className={`mb-3 rounded border px-3 py-2 text-xs ${flash.ok ? 'border-status/40 bg-status/10 text-status' : 'border-operations/40 bg-operations/10 text-operations'}`}>
          {flash.msg}
        </div>
      )}

      <ul className="flex flex-col gap-2">
        {missions.map(m => (
          <li key={m.mission_id} className="rounded border border-edge bg-panel-2/60 p-3">
            <div className="flex items-start justify-between gap-2 mb-2">
              <div>
                <span className="font-mono text-[10px] text-lcars-muted">{shortId(m.mission_id)}</span>
                <p className="text-xs font-medium text-lcars-text leading-snug mt-0.5">{m.title}</p>
                <p className="text-[10px] text-lcars-muted mt-0.5">{m.status}{m.priority ? ` · ${m.priority}` : ''}{m.created_by ? ` · ${m.created_by}` : ''}</p>
              </div>
            </div>

            {rejectReasonFor === m.mission_id ? (
              <div className="mt-2 flex flex-col gap-2">
                <input
                  type="text"
                  placeholder="Rejection reason (required)"
                  value={rejectReason}
                  onChange={e => setRejectReason(e.target.value)}
                  className="w-full rounded border border-edge bg-panel px-2 py-1.5 text-xs text-lcars-text placeholder:text-lcars-muted focus:border-operations/60 focus:outline-none"
                />
                <div className="flex gap-2">
                  <button
                    disabled={!rejectReason.trim() || acting === m.mission_id}
                    onClick={() => decide(m.mission_id, 'reject', rejectReason.trim())}
                    className="flex-1 rounded border border-operations/60 bg-operations/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-operations hover:bg-operations/20 disabled:opacity-40 transition-colors"
                  >
                    {acting === m.mission_id ? 'Rejecting…' : 'Confirm Reject'}
                  </button>
                  <button
                    onClick={() => { setRejectReasonFor(null); setRejectReason(''); }}
                    className="rounded border border-edge px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-lcars-muted hover:text-lcars-text transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2 mt-2">
                <button
                  disabled={acting === m.mission_id}
                  onClick={() => decide(m.mission_id, 'approve')}
                  className="flex-1 rounded border border-status/60 bg-status/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-status hover:bg-status/20 disabled:opacity-40 transition-colors"
                >
                  {acting === m.mission_id ? 'Working…' : 'Approve'}
                </button>
                <button
                  disabled={acting === m.mission_id}
                  onClick={() => setRejectReasonFor(m.mission_id)}
                  className="flex-1 rounded border border-operations/40 bg-operations/5 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-operations hover:bg-operations/10 disabled:opacity-40 transition-colors"
                >
                  Reject
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
