'use client';

/**
 * Mission Workbench detail — look-and-feel migration of
 * (app)/missions/[id]. All mutation routing (PATCH /api/missions/{id},
 * POST .../approve, POST .../reject) and eligibility gating are unchanged
 * from the LCARS original — see that file for the version this replaces
 * and the MSN-0305/MSN-0328/MSN-0351 history behind each of these choices.
 */

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { Badge, Button, Card, Textarea } from '@/components/ui';
import { WorkbenchShell } from '@/components/ui';
import { ApprovalQueue, type ApprovalQueueFlash } from '../_components/ApprovalQueue';
import { STATUS_OPTIONS, APPROVAL_ELIGIBLE, REJECTION_ELIGIBLE, statusToBadge, fmtDate } from '../_components/shared';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import type { Mission } from '@/lib/types';

function Field({ label, value, mono }: { label: string; value?: string | null; mono?: boolean }) {
  if (!value) return null;
  return (
    <div className="flex flex-col gap-0.5">
      <p className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2">{label}</p>
      <p className={`break-all text-[13px] text-wb-ink ${mono ? 'font-mono text-[12px]' : ''}`}>{value}</p>
    </div>
  );
}

export default function MissionWorkbenchDetailPage() {
  const { id } = useParams<{ id: string }>();

  const [mission, setMission] = useState<Mission | null>(null);
  // MSN-0351: distinguish loading / found / genuinely-not-found (404) / fetch
  // error, same as the LCARS original — no mock-data fallback.
  const [loadState, setLoadState] = useState<'loading' | 'found' | 'notfound' | 'error'>('loading');
  const [newStatus, setNewStatus] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [deciding, setDeciding] = useState(false);
  const [decisionFlash, setDecisionFlash] = useState<ApprovalQueueFlash | null>(null);

  useEffect(() => {
    async function load() {
      const supabase = createSupabaseBrowserClient();
      const { data, error } = await supabase
        .from('missions')
        .select('*')
        .eq('mission_id', id)
        .single();

      if (data) {
        setMission(data as Mission);
        setNewStatus(data.status);
        setLoadState('found');
      } else if (error && error.code === 'PGRST116') {
        setLoadState('notfound');
      } else if (error) {
        console.error('mission detail fetch failed', error);
        setLoadState('error');
      } else {
        setLoadState('notfound');
      }
    }
    load();
  }, [id]);

  async function handleSave() {
    if (!mission) return;
    setSaving(true);
    setError(null);

    // MSN-0305: governed, audited server-side update — same route, same body
    // shape as the LCARS original.
    const res = await fetch(`/api/missions/${encodeURIComponent(mission.mission_id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus, notes: note.trim() || undefined }),
    });

    setSaving(false);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(body.detail ?? body.error ?? `Update failed (${res.status})`);
    } else {
      setSaved(true);
      setMission({ ...mission, status: newStatus });
      setNote('');
      setTimeout(() => setSaved(false), 2000);
    }
  }

  async function decide(decision: 'approve' | 'reject', reason?: string) {
    if (!mission) return;
    setDeciding(true);
    try {
      const resp = await fetch(`/api/missions/${encodeURIComponent(mission.mission_id)}/${decision}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'lcars-portal:mission-workbench', owner: 'Captain', ...(reason ? { reason } : {}) }),
      });
      const data = await resp.json();
      if (resp.ok) {
        setDecisionFlash({ id: mission.mission_id, message: decision === 'approve' ? 'Approved' : 'Requires Rework', ok: true });
        setMission({ ...mission, status: data.new_status });
        setNewStatus(data.new_status);
      } else {
        setDecisionFlash({ id: mission.mission_id, message: data.error ?? 'Decision failed', ok: false });
      }
    } catch (e) {
      setDecisionFlash({ id: mission.mission_id, message: String(e), ok: false });
    } finally {
      setDeciding(false);
      setTimeout(() => setDecisionFlash(null), 4000);
    }
  }

  if (loadState === 'loading') {
    return (
      <WorkbenchShell title="Mission Workbench" eyebrow="Loading" homeHref="/mission-workbench" homeAriaLabel="Mission Workbench home" tagline="USS TJR · Mission Workbench · Registry — capacity-aware filtering, governed approve/reject">
        <p className="py-16 text-center text-[13px] text-wb-ink2">Loading mission…</p>
      </WorkbenchShell>
    );
  }

  if (loadState === 'error') {
    return (
      <WorkbenchShell title="Mission Data Unavailable" eyebrow="Fetch error" homeHref="/mission-workbench" homeAriaLabel="Mission Workbench home" tagline="USS TJR · Mission Workbench · Registry — capacity-aware filtering, governed approve/reject" back={{ href: '/mission-workbench', label: 'Mission Registry' }}>
        <Card>
          <div className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3">
            <p className="text-[13px] font-semibold text-wb-crit-on">Couldn&rsquo;t load this mission right now.</p>
            <p className="mt-1 text-[12px] text-wb-ink2">
              This is a load failure — not a confirmation the mission is missing. No record is shown
              because the registry could not be read. Retry shortly.
            </p>
          </div>
        </Card>
      </WorkbenchShell>
    );
  }

  if (loadState === 'notfound' || !mission) {
    return (
      <WorkbenchShell title="Mission Not Found" eyebrow="No such record" homeHref="/mission-workbench" homeAriaLabel="Mission Workbench home" tagline="USS TJR · Mission Workbench · Registry — capacity-aware filtering, governed approve/reject" back={{ href: '/mission-workbench', label: 'Mission Registry' }}>
        <Card>
          <p className="text-[13px] text-wb-ink2">
            No mission with ID <span className="font-mono text-wb-ink">{id}</span> exists in the registry.
          </p>
        </Card>
      </WorkbenchShell>
    );
  }

  const eyebrow = [mission.mission_type, mission.task_type].filter(Boolean).join(' · ') || 'Mission';

  return (
    <WorkbenchShell title={mission.mission_id} eyebrow={eyebrow} homeHref="/mission-workbench" homeAriaLabel="Mission Workbench home" tagline="USS TJR · Mission Workbench · Registry — capacity-aware filtering, governed approve/reject" back={{ href: '/mission-workbench', label: 'Mission Registry' }} right={<Badge status={statusToBadge(mission.status)}>{mission.status}</Badge>}>
      <div className="flex flex-col gap-4">
        <Card>
          <h2 className="font-serif text-xl text-wb-ink">{mission.title}</h2>
          {mission.description && (
            <p className="mt-2 text-[13px] leading-relaxed text-wb-ink2">{mission.description}</p>
          )}
          <div className="mt-3 flex flex-wrap gap-3 items-center">
            {mission.priority && <Badge status="neutral">{mission.priority}</Badge>}
            {mission.created_by && (
              <span className="text-[12px] text-wb-ink2">Created by <span className="text-wb-ink">{mission.created_by}</span></span>
            )}
          </div>
        </Card>

        <Card title="Mission Details">
          <div className="grid grid-cols-2 gap-x-6 gap-y-4">
            <Field label="Mission ID" value={mission.mission_id} />
            <Field label="Status" value={mission.status} />
            <Field label="Mission Type" value={mission.mission_type} />
            <Field label="Task Type" value={mission.task_type} />
            <Field label="Priority" value={mission.priority} />
            <Field label="Created" value={fmtDate(mission.created_at)} />
            <Field label="Last Updated" value={fmtDate(mission.updated_at)} />
            <Field label="Closed" value={fmtDate(mission.closed_at)} />
            {mission.outcome_rating != null && <Field label="Outcome Rating" value={String(mission.outcome_rating)} />}
            {mission.rework_of && <Field label="Rework Of" value={mission.rework_of} />}
          </div>
          <Link
            href={`/comms-studio?type=mission_report&refId=${encodeURIComponent(mission.mission_id)}`}
            className="mt-4 inline-block text-[12px] text-wb-sage-deep underline underline-offset-2 hover:text-wb-ink"
          >
            Draft a Mission Report →
          </Link>
        </Card>

        {(APPROVAL_ELIGIBLE.includes(mission.status) || REJECTION_ELIGIBLE.includes(mission.status)) && (
          <ApprovalQueue
            title="Governed Decision"
            items={[{
              id: mission.mission_id,
              title: mission.title,
              detail: `Current status: ${mission.status}`,
              canApprove: APPROVAL_ELIGIBLE.includes(mission.status),
              canReject: REJECTION_ELIGIBLE.includes(mission.status),
            }]}
            actingId={deciding ? mission.mission_id : null}
            flash={decisionFlash}
            onApprove={() => decide('approve')}
            onReject={(_id, reason) => decide('reject', reason)}
          />
        )}

        {(mission.repo || mission.branch_name || mission.pr_url) && (
          <Card title="Engineering">
            <div className="flex flex-col gap-3">
              <Field label="Repository" value={mission.repo} mono />
              <Field label="Branch" value={mission.branch_name} mono />
              {mission.pr_url && (
                <div className="flex flex-col gap-0.5">
                  <p className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2">Pull Request</p>
                  <a
                    href={mission.pr_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="break-all font-mono text-[12px] text-wb-sage-deep hover:underline"
                  >
                    {mission.pr_url}
                  </a>
                </div>
              )}
            </div>
          </Card>
        )}

        <Card title="Update Status">
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <p className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2">New status</p>
              <div className="flex flex-wrap gap-2">
                {STATUS_OPTIONS.map(s => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setNewStatus(s)}
                    className={`rounded-md border px-3 py-1.5 text-[12px] font-semibold transition-colors focus-visible:outline
                      focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${
                      newStatus === s
                        ? 'border-wb-sage-deep bg-wb-sage-deep/10 text-wb-sage-deep'
                        : 'border-wb-line bg-wb-bg text-wb-ink2 hover:border-wb-sage-deep/50'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            <Textarea
              label="Note (optional)"
              value={note}
              onChange={e => setNote(e.target.value)}
              rows={2}
              placeholder="What changed? What's the blocker?"
            />

            {error && <p className="text-[12px] text-wb-crit-on">{error}</p>}

            <Button
              onClick={handleSave}
              disabled={saving || (newStatus === mission.status && !note)}
              className="w-full"
            >
              {saving ? 'Saving…' : saved ? '✓ Saved' : 'Update Mission'}
            </Button>
          </div>
        </Card>
      </div>
    </WorkbenchShell>
  );
}
