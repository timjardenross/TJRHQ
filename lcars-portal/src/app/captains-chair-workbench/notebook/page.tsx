'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';
import { WorkbenchBadge } from '@/components/WorkbenchBadge';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import type { StatusTone } from '@/lib/types';

// ── Types ─────────────────────────────────────────────────────────────────────

interface IntelligenceNote {
  id: string;
  title: string | null;
  raw_content: string;
  source: string;
  tags: string[];
  status: string;
  created_at: string;
  updated_at: string;
  assigned_officers: string[];
  officer_findings: Record<string, unknown>;
  triage_summary: string | null;
  classification: string | null;
  confidence_score: number | null;
  strategic_alignment_score: number | null;
  recommended_route: string | null;
  routed_to_type: string | null;
  routed_to_id: string | null;
  routed_entity_type: string | null;
  routed_at: string | null;
  routed_by: string | null;
}

type FilterStatus = 'ALL' | 'CAPTURED' | 'OFFICER_REVIEW' | 'NUMBER_ONE_REVIEW' | 'READY_FOR_ROUTING' | 'ROUTED' | 'ARCHIVED';

// ── Helpers ───────────────────────────────────────────────────────────────────

// Workflow-stage labels, not health/severity states — kept on the
// department-flavored StatusTone system (rendered via toneClasses(), the
// same function WorkbenchBadge itself uses) rather than force-fit onto
// StateTone ok/warn/crit, which would misrepresent "just captured, not yet
// triaged" as some kind of alarm state.
function statusTone(status: string): StatusTone {
  switch (status) {
    case 'CAPTURED':           return 'neutral';
    case 'OFFICER_REVIEW':     return 'science';
    case 'NUMBER_ONE_REVIEW':  return 'operations';
    case 'READY_FOR_ROUTING':  return 'command';
    case 'ROUTED':             return 'status';
    case 'ARCHIVED':           return 'neutral';
    default:                   return 'neutral';
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'CAPTURED':           return 'Captured';
    case 'OFFICER_REVIEW':     return 'Officer Review';
    case 'NUMBER_ONE_REVIEW':  return 'Number One Review';
    case 'READY_FOR_ROUTING':  return 'Ready for Routing';
    case 'ROUTED':             return 'Routed';
    case 'ARCHIVED':           return 'Archived';
    default:                   return status;
  }
}

function relativeAge(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 60)    return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)     return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function routeLabel(route: string | null): string | null {
  if (!route) return null;
  switch (route) {
    case 'captain':    return '→ Captain decision';
    case 'xo':        return '→ XO action';
    case 'number_one': return '→ Number One';
    case 'officer':    return '→ Officer domain';
    case 'knowledge':  return '→ Knowledge capture';
    case 'archive':    return '→ Archive';
    default:           return `→ ${route}`;
  }
}

// ── Artefact navigation ────────────────────────────────────────────────────────

// MSN-0335: 4 of these 7 pointed at pages that have never existed
// (/strategy, /decisions, /lessons, /research) — dead links waiting to
// fire the moment any of those route types actually got routed. Fixed
// 2 to their real destination (/knowledge's own nav description
// already claims "Decisions, lessons, architecture, articles" as its
// territory); removed the other 2 rather than guess at a destination
// that doesn't exist — ArtefactLink already falls back to plain text
// when no mapping is present, so this is a safe reduction, not a
// regression.
const _ARTEFACT_NAV: Record<string, string> = {
  MISSION:                  '/missions',
  BUILD_REQUEST:            '/engineering',
  IMPROVEMENT:              '/knowledge-workbench?domain=memory',
  KNOWLEDGE_ARTICLE:        '/knowledge-workbench?domain=memory',
  COMMUNICATION_OPPORTUNITY: '/comms',
};

function ArtefactLink({ entityType, artefactId }: { entityType: string | null; artefactId: string }) {
  const base = entityType ? _ARTEFACT_NAV[entityType] : null;
  return base ? (
    <Link
      href={base}
      className="text-xs text-wb-ink font-mono hover:text-wb-sage-deep underline underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
    >
      {artefactId}
    </Link>
  ) : (
    <p className="text-xs text-wb-ink font-mono">{artefactId}</p>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

const FILTER_TABS: { key: FilterStatus; label: string }[] = [
  { key: 'ALL',               label: 'All' },
  { key: 'CAPTURED',          label: 'Captured' },
  { key: 'OFFICER_REVIEW',    label: 'In Review' },
  { key: 'READY_FOR_ROUTING', label: 'Ready' },
  { key: 'ROUTED',            label: 'Routed' },
  { key: 'ARCHIVED',          label: 'Archived' },
];

function NoteCard({
  note,
  expanded,
  onToggle,
  onArchive,
  onApproveRoute,
  archiving,
  routing,
  routeMessage,
}: {
  note: IntelligenceNote;
  expanded: boolean;
  onToggle: () => void;
  onArchive: () => void;
  onApproveRoute: () => void;
  archiving: boolean;
  routing: boolean;
  routeMessage: { id: string; ok: boolean; text: string } | null;
}) {
  const canRoute = note.status === 'READY_FOR_ROUTING' && !!note.recommended_route;
  const isArchived = note.status === 'ARCHIVED';

  return (
    <div className="overflow-hidden rounded-lg border border-wb-line bg-wb-bg/60">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-start gap-3 p-3 text-left hover:bg-wb-border/30 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
      >
        <div className="flex flex-col items-start gap-1.5 flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <WorkbenchBadge label={statusLabel(note.status)} tone={statusTone(note.status)} />
            {note.classification && (
              <span className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2 border border-wb-line rounded px-1.5 py-0.5">
                {note.classification}
              </span>
            )}
            {canRoute && (
              <span className="text-[10px] uppercase tracking-[0.2em] text-wb-sage-deep">
                {routeLabel(note.recommended_route)}
              </span>
            )}
          </div>
          <p className="text-sm font-semibold text-wb-ink truncate w-full">
            {note.title || note.raw_content.slice(0, 60) + (note.raw_content.length > 60 ? '…' : '')}
          </p>
          <div className="flex items-center gap-3 text-[10px] text-wb-ink2">
            <span>{relativeAge(note.created_at)}</span>
            {note.tags.length > 0 && (
              <span>{note.tags.slice(0, 3).join(' · ')}</span>
            )}
            {note.assigned_officers.length > 0 && (
              <span>Officers: {note.assigned_officers.join(', ')}</span>
            )}
          </div>
        </div>
        <span aria-hidden="true" className="text-wb-ink2 text-xs shrink-0 mt-1">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="border-t border-wb-line px-3 pb-3 pt-3 flex flex-col gap-3">
          <div>
            <p className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2 mb-1">Raw Content</p>
            <p className="text-sm text-wb-ink leading-relaxed whitespace-pre-wrap">{note.raw_content}</p>
          </div>

          {note.triage_summary && (
            <div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2 mb-1">Triage Summary</p>
              <p className="text-sm text-wb-ink/80 leading-relaxed">{note.triage_summary}</p>
            </div>
          )}

          {Object.keys(note.officer_findings).length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2 mb-1">Officer Findings</p>
              <div className="flex flex-col gap-1.5">
                {Object.entries(note.officer_findings).map(([officer, finding]) => (
                  <div key={officer} className="rounded border border-wb-sage-deep/20 bg-wb-sage-deep/5 px-2 py-1.5">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-wb-sage-deep mb-0.5">{officer}</p>
                    <p className="text-xs text-wb-ink/80">
                      {typeof finding === 'object' && finding !== null
                        ? (finding as Record<string, unknown>).recommendation as string ?? JSON.stringify(finding)
                        : String(finding)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(note.strategic_alignment_score !== null || note.confidence_score !== null) && (
            <div className="grid grid-cols-3 gap-2">
              {note.strategic_alignment_score !== null && (
                <div className="rounded border border-wb-line bg-wb-bg/60 px-2 py-1.5 text-center">
                  <p className="text-[9px] uppercase tracking-wider text-wb-ink2">Strategic</p>
                  <p className="font-sans text-base font-bold text-wb-sage-deep">
                    {Math.round(note.strategic_alignment_score * 100)}
                  </p>
                </div>
              )}
              {note.confidence_score !== null && (
                <div className="rounded border border-wb-line bg-wb-bg/60 px-2 py-1.5 text-center">
                  <p className="text-[9px] uppercase tracking-wider text-wb-ink2">Confidence</p>
                  <p className="font-sans text-base font-bold text-wb-ink">
                    {Math.round(note.confidence_score * 100)}
                  </p>
                </div>
              )}
            </div>
          )}

          {note.routed_to_id && (
            <div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2 mb-1">Artefact Created</p>
              <div className="rounded border border-wb-ok/20 bg-wb-ok/5 px-2 py-1.5 flex flex-col gap-0.5">
                {note.routed_entity_type && (
                  <p className="text-[10px] uppercase tracking-wider text-wb-ok-on font-semibold">{note.routed_entity_type.replace(/_/g, ' ')}</p>
                )}
                <ArtefactLink entityType={note.routed_entity_type} artefactId={note.routed_to_id} />
                {note.routed_by && (
                  <p className="text-[10px] text-wb-ink2">via {note.routed_by}{note.routed_at ? ` · ${relativeAge(note.routed_at)}` : ''}</p>
                )}
              </div>
            </div>
          )}

          {routeMessage && (
            <div className={`rounded border px-3 py-2 text-xs ${routeMessage.ok ? 'border-wb-ok/40 bg-wb-ok/10 text-wb-ok-on' : 'border-wb-crit/40 bg-wb-crit/10 text-wb-crit-on'}`}>
              {routeMessage.text}
            </div>
          )}

          {!isArchived && (
            <div className="flex gap-2 pt-1">
              {canRoute && (
                <button
                  type="button"
                  onClick={onApproveRoute}
                  disabled={routing}
                  className="rounded-lg border border-wb-sage-deep bg-wb-sage-deep/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] text-wb-sage-deep hover:bg-wb-sage-deep/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                >
                  {routing ? 'Routing…' : `Approve ${routeLabel(note.recommended_route)}`}
                </button>
              )}
              <button
                type="button"
                onClick={onArchive}
                disabled={archiving}
                className="rounded-lg border border-wb-line px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] text-wb-ink2 hover:border-wb-ink2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
              >
                {archiving ? 'Archiving…' : 'Archive'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CaptainsNotebookWorkbenchPage() {
  const supabase = createSupabaseBrowserClient();

  // Capture form
  const [captureTitle, setCaptureTitle]     = useState('');
  const [captureContent, setCaptureContent] = useState('');
  const [captureTags, setCaptureTags]       = useState('');
  const [capturing, setCapturing]           = useState(false);
  const [captureError, setCaptureError]     = useState<string | null>(null);
  const [captureSuccess, setCaptureSuccess] = useState(false);
  const [quickMode, setQuickMode]           = useState(false);
  const quickRef = useRef<HTMLTextAreaElement>(null);

  // Inbox
  const [notes, setNotes]         = useState<IntelligenceNote[]>([]);
  const [loading, setLoading]     = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [filter, setFilter]       = useState<FilterStatus>('ALL');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [archivingId, setArchivingId] = useState<string | null>(null);
  const [routingId, setRoutingId]   = useState<string | null>(null);
  const [routeMessage, setRouteMessage] = useState<{ id: string; ok: boolean; text: string } | null>(null);

  async function loadNotes() {
    setLoading(true);
    setLoadError(null);
    try {
      const { data, error } = await supabase
        .from('intelligence_notes')
        .select('id, title, raw_content, source, tags, status, created_at, updated_at, assigned_officers, officer_findings, triage_summary, classification, confidence_score, strategic_alignment_score, recommended_route, routed_to_type, routed_to_id, routed_entity_type, routed_at, routed_by')
        .order('created_at', { ascending: false })
        .limit(100);
      // A genuine query error must be surfaced — not silently swallowed into an
      // empty inbox that reads as "no notes yet".
      if (error) {
        setLoadError(error.message);
      } else {
        setNotes((data as IntelligenceNote[]) ?? []);
      }
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadNotes(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (quickMode) quickRef.current?.focus();
  }, [quickMode]);

  async function handleCapture() {
    if (!captureContent.trim()) return;
    setCapturing(true);
    setCaptureError(null);

    const tags = captureTags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const { error } = await supabase.from('intelligence_notes').insert({
      title:       captureTitle.trim() || null,
      raw_content: captureContent.trim(),
      tags,
      source:      'manual',
      status:      'CAPTURED',
    });

    setCapturing(false);
    if (error) {
      setCaptureError(error.message);
    } else {
      setCaptureSuccess(true);
      setCaptureTitle('');
      setCaptureContent('');
      setCaptureTags('');
      setTimeout(() => setCaptureSuccess(false), 2000);
      loadNotes();
    }
  }

  async function handleArchive(id: string) {
    setArchivingId(id);
    await supabase
      .from('intelligence_notes')
      .update({ status: 'ARCHIVED' })
      .eq('id', id);
    setArchivingId(null);
    loadNotes();
  }

  async function handleApproveRoute(note: IntelligenceNote) {
    setRoutingId(note.id);
    // MSN-0334: was a direct client-side update that only ever set
    // status/routed_to_type -- never actually created the artefact the
    // UI implied. Now calls a real API route that creates a real
    // mission for MISSION-routed notes, or honestly reports that
    // automatic creation isn't wired for other route types yet.
    try {
      const res = await fetch(`/api/intelligence-notes/${encodeURIComponent(note.id)}/approve-route`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok) {
        setRouteMessage({ id: note.id, ok: false, text: data.error ?? 'Approve route failed' });
      } else if (data.artefact_created) {
        setRouteMessage({ id: note.id, ok: true, text: `Created ${data.entity_type.toLowerCase()} ${data.artefact_id}.` });
      } else {
        setRouteMessage({ id: note.id, ok: true, text: data.note ?? 'Routing decision recorded.' });
      }
    } catch (e) {
      setRouteMessage({ id: note.id, ok: false, text: e instanceof Error ? e.message : String(e) });
    }
    setRoutingId(null);
    loadNotes();
    setTimeout(() => setRouteMessage(null), 8000);
  }

  const filtered = filter === 'ALL'
    ? notes.filter((n) => n.status !== 'ARCHIVED')
    : notes.filter((n) => n.status === filter);

  const readyCount = notes.filter((n) => n.status === 'READY_FOR_ROUTING').length;
  const capturedCount = notes.filter((n) => n.status === 'CAPTURED').length;

  return (
    <WorkbenchShell
      title="Captain's Notebook"
      eyebrow="Intelligence Intake & Refinement"
      tagline="USS TJR · Captain's Notebook · Intelligence Intake & Refinement"
      back={{ href: '/captains-chair-workbench', label: "Captain's Chair" }}
    >
      <div className="flex flex-col gap-4">
        {/* Header */}
        <WorkbenchPanel title="Captain's Notebook" eyebrow="EXEC-010B · Intelligence Intake & Refinement">
          <p className="text-xs text-wb-ink2 leading-relaxed">
            Capture rough thoughts. The Officer Corps refines them — classifying, scoring, and routing to the right action.
            {readyCount > 0 && (
              <span className="ml-2 font-semibold text-wb-sage-deep">
                {readyCount} note{readyCount !== 1 ? 's' : ''} ready for routing.
              </span>
            )}
          </p>
        </WorkbenchPanel>

        {/* Quick Capture */}
        <WorkbenchPanel
          title="Quick Capture"
          eyebrow="Raw thought → Officer Corps"
          actions={
            <button
              type="button"
              onClick={() => setQuickMode(!quickMode)}
              className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2 hover:text-wb-sage-deep transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
            >
              {quickMode ? 'Full form' : 'Quick mode'}
            </button>
          }
        >
          {quickMode ? (
            /* ── One-tap mobile capture ─────────────────────────────── */
            <div className="flex flex-col gap-3">
              <textarea
                ref={quickRef}
                value={captureContent}
                onChange={(e) => setCaptureContent(e.target.value)}
                rows={5}
                placeholder="Capture the thought. Officers will refine and route it."
                className="w-full rounded-lg border border-wb-sage-deep bg-white px-3 py-3 text-base text-wb-ink placeholder:text-wb-ink2 resize-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    if (captureContent.trim() && !capturing) handleCapture();
                  }
                }}
              />
              {captureError && <p className="text-xs text-wb-crit-on">{captureError}</p>}
              <button
                type="button"
                onClick={handleCapture}
                disabled={capturing || !captureContent.trim()}
                className="w-full rounded-lg bg-wb-sage-deep px-4 py-3.5 font-sans text-base font-bold uppercase tracking-[0.2em] text-white transition-opacity hover:opacity-80 disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-ink"
              >
                {captureSuccess ? (<><span aria-hidden="true">✓ </span>Captured</>) : capturing ? 'Capturing…' : 'Capture'}
              </button>
              <p className="text-[10px] text-wb-ink2 text-center">⌘↵ or Ctrl↵ to capture</p>
            </div>
          ) : (
            /* ── Full form ──────────────────────────────────────────── */
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <p className="text-[10px] uppercase tracking-[0.25em] text-wb-ink2">Title (optional)</p>
                <input
                  type="text"
                  value={captureTitle}
                  onChange={(e) => setCaptureTitle(e.target.value)}
                  placeholder="Leave blank to auto-title from content"
                  className="w-full rounded-lg border border-wb-line bg-white px-3 py-2 text-sm text-wb-ink placeholder:text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                />
              </div>
              <div className="flex flex-col gap-1">
                <p className="text-[10px] uppercase tracking-[0.25em] text-wb-ink2">Thought or intelligence</p>
                <textarea
                  value={captureContent}
                  onChange={(e) => setCaptureContent(e.target.value)}
                  rows={4}
                  placeholder="Capture the raw thought. Officers will determine what it means, why it matters, and where it routes."
                  className="w-full rounded-lg border border-wb-line bg-white px-3 py-2 text-sm text-wb-ink placeholder:text-wb-ink2 resize-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                />
              </div>
              <div className="flex flex-col gap-1">
                <p className="text-[10px] uppercase tracking-[0.25em] text-wb-ink2">Tags (comma-separated, optional)</p>
                <input
                  type="text"
                  value={captureTags}
                  onChange={(e) => setCaptureTags(e.target.value)}
                  placeholder="strategy, delivery, health…"
                  className="w-full rounded-lg border border-wb-line bg-white px-3 py-2 text-sm text-wb-ink placeholder:text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                />
              </div>
              {captureError && <p className="text-xs text-wb-crit-on">{captureError}</p>}
              <button
                type="button"
                onClick={handleCapture}
                disabled={capturing || !captureContent.trim()}
                className="w-full rounded-lg bg-wb-sage-deep px-4 py-2.5 font-sans text-sm font-bold uppercase tracking-[0.2em] text-white transition-opacity hover:opacity-80 disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-ink"
              >
                {captureSuccess ? (<><span aria-hidden="true">✓ </span>Captured</>) : capturing ? 'Capturing…' : 'Capture'}
              </button>
            </div>
          )}
        </WorkbenchPanel>

        {/* Inbox */}
        <WorkbenchPanel
          title="Intelligence Inbox"
          eyebrow={`${notes.filter((n) => n.status !== 'ARCHIVED').length} active · ${capturedCount} pending triage`}
          actions={
            <button
              type="button"
              onClick={loadNotes}
              className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2 hover:text-wb-sage-deep transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
            >
              Refresh
            </button>
          }
        >
          {/* Filter tabs */}
          <div className="flex flex-wrap gap-1.5 mb-4">
            {FILTER_TABS.map((tab) => {
              const count = tab.key === 'ALL'
                ? notes.filter((n) => n.status !== 'ARCHIVED').length
                : notes.filter((n) => n.status === tab.key).length;
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setFilter(tab.key)}
                  className={[
                    'rounded-lg border px-2.5 py-1 text-[10px] uppercase tracking-[0.2em] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep',
                    filter === tab.key
                      ? 'border-wb-sage-deep bg-wb-sage-deep/10 text-wb-sage-deep'
                      : 'border-wb-line text-wb-ink2 hover:border-wb-ink2'
                  ].join(' ')}
                >
                  {tab.label} ({count})
                </button>
              );
            })}
          </div>

          {loading ? (
            <p className="text-sm text-wb-ink2 text-center py-6">Loading…</p>
          ) : loadError ? (
            <div className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 px-3 py-4 text-sm text-wb-crit-on text-center">
              Couldn&apos;t load notebook entries — try again.
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-wb-ink2 text-center py-6">
              {filter === 'ALL' ? 'No intelligence notes yet. Capture a thought above.' : `No notes in ${statusLabel(filter)}.`}
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {filtered.map((note) => (
                <NoteCard
                  key={note.id}
                  note={note}
                  expanded={expandedId === note.id}
                  onToggle={() => setExpandedId(expandedId === note.id ? null : note.id)}
                  onArchive={() => handleArchive(note.id)}
                  onApproveRoute={() => handleApproveRoute(note)}
                  archiving={archivingId === note.id}
                  routing={routingId === note.id}
                  routeMessage={routeMessage?.id === note.id ? routeMessage : null}
                />
              ))}
            </div>
          )}
        </WorkbenchPanel>
      </div>
    </WorkbenchShell>
  );
}
