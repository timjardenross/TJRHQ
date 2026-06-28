'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
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

const _ARTEFACT_NAV: Record<string, string> = {
  MISSION:                  '/missions',
  BUILD_REQUEST:            '/engineering',
  STRATEGIC_INITIATIVE:     '/strategy',
  IMPROVEMENT:              '/decisions',
  KNOWLEDGE_ARTICLE:        '/lessons',
  RESEARCH_REQUEST:         '/research',
  COMMUNICATION_OPPORTUNITY: '/comms',
};

function ArtefactLink({ entityType, artefactId }: { entityType: string | null; artefactId: string }) {
  const base = entityType ? _ARTEFACT_NAV[entityType] : null;
  return base ? (
    <Link
      href={base}
      className="text-xs text-lcars-text font-mono hover:text-status-on underline underline-offset-2"
    >
      {artefactId}
    </Link>
  ) : (
    <p className="text-xs text-lcars-text font-mono">{artefactId}</p>
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
}: {
  note: IntelligenceNote;
  expanded: boolean;
  onToggle: () => void;
  onArchive: () => void;
  onApproveRoute: () => void;
  archiving: boolean;
  routing: boolean;
}) {
  const canRoute = note.status === 'READY_FOR_ROUTING' && !!note.recommended_route;
  const isArchived = note.status === 'ARCHIVED';

  return (
    <div className="rounded-lcars border border-edge bg-panel-2/40 overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-start gap-3 p-3 text-left hover:bg-edge/10 transition-colors"
      >
        <div className="flex flex-col items-start gap-1.5 flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge label={statusLabel(note.status)} tone={statusTone(note.status)} />
            {note.classification && (
              <span className="text-[10px] uppercase tracking-[0.2em] text-science-on border border-science/30 rounded px-1.5 py-0.5">
                {note.classification}
              </span>
            )}
            {canRoute && (
              <span className="text-[10px] uppercase tracking-[0.2em] text-command-on">
                {routeLabel(note.recommended_route)}
              </span>
            )}
          </div>
          <p className="text-sm font-semibold text-lcars-text truncate w-full">
            {note.title || note.raw_content.slice(0, 60) + (note.raw_content.length > 60 ? '…' : '')}
          </p>
          <div className="flex items-center gap-3 text-[10px] text-lcars-muted">
            <span>{relativeAge(note.created_at)}</span>
            {note.tags.length > 0 && (
              <span>{note.tags.slice(0, 3).join(' · ')}</span>
            )}
            {note.assigned_officers.length > 0 && (
              <span>Officers: {note.assigned_officers.join(', ')}</span>
            )}
          </div>
        </div>
        <span className="text-lcars-muted text-xs shrink-0 mt-1">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="border-t border-edge px-3 pb-3 pt-3 flex flex-col gap-3">
          <div>
            <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted mb-1">Raw Content</p>
            <p className="text-sm text-lcars-text leading-relaxed whitespace-pre-wrap">{note.raw_content}</p>
          </div>

          {note.triage_summary && (
            <div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted mb-1">Triage Summary</p>
              <p className="text-sm text-lcars-text/80 leading-relaxed">{note.triage_summary}</p>
            </div>
          )}

          {Object.keys(note.officer_findings).length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted mb-1">Officer Findings</p>
              <div className="flex flex-col gap-1.5">
                {Object.entries(note.officer_findings).map(([officer, finding]) => (
                  <div key={officer} className="rounded border border-science/20 bg-science/5 px-2 py-1.5">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-science-on mb-0.5">{officer}</p>
                    <p className="text-xs text-lcars-text/80">
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
                <div className="rounded border border-edge bg-panel/60 px-2 py-1.5 text-center">
                  <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Strategic</p>
                  <p className="font-lcars text-base font-bold text-command-on">
                    {Math.round(note.strategic_alignment_score * 100)}
                  </p>
                </div>
              )}
              {note.confidence_score !== null && (
                <div className="rounded border border-edge bg-panel/60 px-2 py-1.5 text-center">
                  <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Confidence</p>
                  <p className="font-lcars text-base font-bold text-science-on">
                    {Math.round(note.confidence_score * 100)}
                  </p>
                </div>
              )}
            </div>
          )}

          {note.routed_to_id && (
            <div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted mb-1">Artefact Created</p>
              <div className="rounded border border-status/20 bg-status/5 px-2 py-1.5 flex flex-col gap-0.5">
                {note.routed_entity_type && (
                  <p className="text-[10px] uppercase tracking-wider text-status-on font-semibold">{note.routed_entity_type.replace(/_/g, ' ')}</p>
                )}
                <ArtefactLink entityType={note.routed_entity_type} artefactId={note.routed_to_id} />
                {note.routed_by && (
                  <p className="text-[10px] text-lcars-muted">via {note.routed_by}{note.routed_at ? ` · ${relativeAge(note.routed_at)}` : ''}</p>
                )}
              </div>
            </div>
          )}

          {!isArchived && (
            <div className="flex gap-2 pt-1">
              {canRoute && (
                <button
                  type="button"
                  onClick={onApproveRoute}
                  disabled={routing}
                  className="rounded-lcars border border-command bg-command/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] text-command-on hover:bg-command/20 transition-colors disabled:opacity-40"
                >
                  {routing ? 'Routing…' : `Approve ${routeLabel(note.recommended_route)}`}
                </button>
              )}
              <button
                type="button"
                onClick={onArchive}
                disabled={archiving}
                className="rounded-lcars border border-edge px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:border-lcars-muted transition-colors disabled:opacity-40"
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

export default function CaptainsNotebookPage() {
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
  const [filter, setFilter]       = useState<FilterStatus>('ALL');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [archivingId, setArchivingId] = useState<string | null>(null);
  const [routingId, setRoutingId]   = useState<string | null>(null);

  async function loadNotes() {
    setLoading(true);
    const { data, error } = await supabase
      .from('intelligence_notes')
      .select('id, title, raw_content, source, tags, status, created_at, updated_at, assigned_officers, officer_findings, triage_summary, classification, confidence_score, strategic_alignment_score, recommended_route, routed_to_type, routed_to_id, routed_entity_type, routed_at, routed_by')
      .order('created_at', { ascending: false })
      .limit(100);
    setLoading(false);
    if (!error && data) setNotes(data as IntelligenceNote[]);
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
    const routeTypeMap: Record<string, string> = {
      captain:    'decision',
      xo:         'decision',
      number_one: 'mission',
      officer:    'mission',
      knowledge:  'knowledge',
      archive:    'archived',
    };
    await supabase
      .from('intelligence_notes')
      .update({
        status:        'ROUTED',
        routed_to_type: routeTypeMap[note.recommended_route ?? ''] ?? 'decision',
      })
      .eq('id', note.id);
    setRoutingId(null);
    loadNotes();
  }

  const filtered = filter === 'ALL'
    ? notes.filter((n) => n.status !== 'ARCHIVED')
    : notes.filter((n) => n.status === filter);

  const readyCount = notes.filter((n) => n.status === 'READY_FOR_ROUTING').length;
  const capturedCount = notes.filter((n) => n.status === 'CAPTURED').length;

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <LCARSPanel
        title="Captain's Notebook"
        accent="command"
        eyebrow="EXEC-010B · Intelligence Intake &amp; Refinement"
      >
        <p className="text-xs text-lcars-muted leading-relaxed">
          Capture rough thoughts. The Officer Corps refines them — classifying, scoring, and routing to the right action.
          {readyCount > 0 && (
            <span className="ml-2 font-semibold text-command-on">
              {readyCount} note{readyCount !== 1 ? 's' : ''} ready for routing.
            </span>
          )}
        </p>
      </LCARSPanel>

      {/* Quick Capture */}
      <LCARSPanel
        title="Quick Capture"
        accent="command"
        eyebrow="Raw thought → Officer Corps"
        actions={
          <button
            type="button"
            onClick={() => setQuickMode(!quickMode)}
            className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:text-command-on transition-colors"
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
              className="w-full rounded-lcars border border-command bg-space px-3 py-3 text-base text-lcars-text placeholder:text-lcars-muted focus:outline-none resize-none"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  if (captureContent.trim() && !capturing) handleCapture();
                }
              }}
            />
            {captureError && <p className="text-xs text-operations-on">{captureError}</p>}
            <button
              type="button"
              onClick={handleCapture}
              disabled={capturing || !captureContent.trim()}
              className="w-full rounded-lcars bg-command px-4 py-3.5 font-lcars text-base font-bold uppercase tracking-[0.2em] text-white transition-opacity hover:opacity-80 disabled:opacity-40"
            >
              {captureSuccess ? '✓ Captured' : capturing ? 'Capturing…' : 'Capture'}
            </button>
            <p className="text-[10px] text-lcars-muted text-center">⌘↵ or Ctrl↵ to capture</p>
          </div>
        ) : (
          /* ── Full form ──────────────────────────────────────────── */
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">Title (optional)</p>
              <input
                type="text"
                value={captureTitle}
                onChange={(e) => setCaptureTitle(e.target.value)}
                placeholder="Leave blank to auto-title from content"
                className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none"
              />
            </div>
            <div className="flex flex-col gap-1">
              <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">Thought or intelligence</p>
              <textarea
                value={captureContent}
                onChange={(e) => setCaptureContent(e.target.value)}
                rows={4}
                placeholder="Capture the raw thought. Officers will determine what it means, why it matters, and where it routes."
                className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none resize-none"
              />
            </div>
            <div className="flex flex-col gap-1">
              <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">Tags (comma-separated, optional)</p>
              <input
                type="text"
                value={captureTags}
                onChange={(e) => setCaptureTags(e.target.value)}
                placeholder="strategy, delivery, health…"
                className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none"
              />
            </div>
            {captureError && <p className="text-xs text-operations-on">{captureError}</p>}
            <button
              type="button"
              onClick={handleCapture}
              disabled={capturing || !captureContent.trim()}
              className="w-full rounded-lcars bg-command px-4 py-2.5 font-lcars text-sm font-bold uppercase tracking-[0.2em] text-white transition-opacity hover:opacity-80 disabled:opacity-40"
            >
              {captureSuccess ? '✓ Captured' : capturing ? 'Capturing…' : 'Capture'}
            </button>
          </div>
        )}
      </LCARSPanel>

      {/* Inbox */}
      <LCARSPanel
        title="Intelligence Inbox"
        accent="science"
        eyebrow={`${notes.filter((n) => n.status !== 'ARCHIVED').length} active · ${capturedCount} pending triage`}
        actions={
          <button
            type="button"
            onClick={loadNotes}
            className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:text-command-on transition-colors"
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
                  'rounded-lcars border px-2.5 py-1 text-[10px] uppercase tracking-[0.2em] transition-colors',
                  filter === tab.key
                    ? 'border-command bg-command/10 text-command-on'
                    : 'border-edge text-lcars-muted hover:border-lcars-muted'
                ].join(' ')}
              >
                {tab.label} ({count})
              </button>
            );
          })}
        </div>

        {loading ? (
          <p className="text-sm text-lcars-muted text-center py-6">Loading…</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-lcars-muted text-center py-6">
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
              />
            ))}
          </div>
        )}
      </LCARSPanel>
    </div>
  );
}
