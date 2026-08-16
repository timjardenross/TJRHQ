'use client';

// MSN-0176: Captain's Chair — live approval queue for missions awaiting decision.
// Calls POST /api/missions/{id}/approve and /reject from the browser.
//
// Data layer only — the rendered queue itself is the canonical ApprovalQueue
// contract (MSN-0315 Phase 1B). Map missions onto ApprovalQueueItem here;
// a second consumer (e.g. build-request approvals) supplies its own mapping
// and handlers instead of forking this file.

import { useCallback, useEffect, useState } from 'react';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { ApprovalQueue, type ApprovalQueueFlash, type ApprovalQueueItem } from './ApprovalQueue';

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

function toItem(m: QueueMission): ApprovalQueueItem {
  return {
    id: m.mission_id,
    code: shortId(m.mission_id),
    title: m.title,
    // MSN-0334: previously no way back to the mission's own record after
    // approving/rejecting here — the Captain had to manually navigate to
    // /missions and find it again.
    href: `/missions/${encodeURIComponent(m.mission_id)}`,
    detail: `${m.status}${m.priority ? ` · ${m.priority}` : ''}${m.created_by ? ` · ${m.created_by}` : ''}`,
  };
}

export function CaptainApprovalQueue() {
  const [missions, setMissions] = useState<QueueMission[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<string | null>(null);
  const [flash, setFlash] = useState<ApprovalQueueFlash | null>(null);

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
        setFlash({ id: missionId, message: decision === 'approve' ? 'Approved' : 'Requires Rework', ok: true });
        setMissions(prev => prev.filter(m => m.mission_id !== missionId));
      } else {
        setFlash({ id: missionId, message: data.error ?? 'Failed', ok: false });
      }
    } catch (e) {
      setFlash({ id: missionId, message: String(e), ok: false });
    } finally {
      setActing(null);
      setTimeout(() => setFlash(null), 4000);
    }
  }, []);

  return (
    <ApprovalQueue
      title="Captain's Queue"
      theme="wb"
      items={missions.map(toItem)}
      loading={loading}
      actingId={acting}
      flash={flash}
      onRefresh={load}
      onApprove={(id) => decide(id, 'approve')}
      onReject={(id, reason) => decide(id, 'reject', reason)}
    />
  );
}
