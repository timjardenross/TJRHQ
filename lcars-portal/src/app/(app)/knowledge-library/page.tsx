'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { StatTile } from '@/components/StatTile';
import { assignCategory } from '@/lib/categoryPropagation';
import type {
  ProcessingDocument,
  ProcessingChunk,
  KnowledgeLibraryStats,
  DocumentCategory,
  DocumentSensitivity,
  ProcessingStatus,
  ReviewDecision,
  ReviewStatus,
} from '@/lib/types';

// USS-TJR-MSN-0205D: Knowledge Library and Memory Approval Queue.
// Browses documents produced by the VM Knowledge Processing Engine
// (MSN-0205C) and is the ONLY UI path that can approve one into Command
// Memory (knowledge_documents) — every decision is still an explicit
// Captain action, never automated. MSN-0331 added checkbox-based batch
// triage (apply one decision to many selected documents) on top of the
// original per-document flow, which remains unchanged below.

const CATEGORY_OPTIONS: DocumentCategory[] = [
  'Financial', 'Legal', 'Health', 'Correspondence', 'Reference',
  'Identity', 'Property', 'Photo', 'Administrative', 'Other',
];
const SENSITIVITY_OPTIONS: DocumentSensitivity[] = ['standard', 'sensitive', 'restricted'];
const STATUS_OPTIONS: ProcessingStatus[] = [
  'received', 'extracted', 'ocr_required', 'ocr_complete',
  'classified', 'summarised', 'embedded', 'failed', 'awaiting_review', 'excluded',
];

const DECISION_LABELS: Record<ReviewDecision, string> = {
  approved_metadata: 'Approve — Metadata Only',
  approved_summary: 'Approve — Summary to Memory',
  approved_chunks: 'Approve — Full Chunk Memory',
  rejected: 'Reject',
  needs_review: 'Mark Needs Review',
};

// USS-TJR-MSN-0206J-1: only these two review_status values are terminal —
// a document 'awaiting_followup' stays open for a later decision.
const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  awaiting_followup: 'Awaiting Follow-Up',
  resolved: 'Resolved',
  rejected: 'Rejected',
};

function formatBytes(n: number | null): string {
  if (!n) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function sensitivityTone(s: DocumentSensitivity): 'status' | 'command' | 'operations' {
  if (s === 'restricted') return 'operations';
  if (s === 'sensitive') return 'command';
  return 'status';
}

// The auth middleware redirects unauthenticated requests to /login (HTML,
// status 200) rather than returning a 401 — including for /api/* routes.
// A plain fetch() follows that redirect transparently, so `resp.ok` is
// true and the body is an HTML page, not JSON. Every call site needs to
// detect this and show "please sign in again" instead of either silently
// showing an empty list or crashing on `resp.json()` parsing HTML.
class ApiAuthError extends Error {}

async function fetchJson(input: string, init?: RequestInit): Promise<any> {
  const resp = await fetch(input, init);
  if (resp.redirected && resp.url.includes('/login')) {
    throw new ApiAuthError('Your session has expired. Please sign in again.');
  }
  let data: unknown = null;
  try {
    data = await resp.json();
  } catch {
    throw new Error(`Unexpected response from server (status ${resp.status}).`);
  }
  if (!resp.ok) {
    const body = data as { error?: string; detail?: string } | null;
    throw new Error(body?.error ?? body?.detail ?? `Request failed (status ${resp.status}).`);
  }
  return data;
}

// MSN-0334: useSearchParams() (added for URL-persisted filters/page/
// selected document) requires a Suspense boundary in the App Router,
// or the build fails to prerender this route.
export default function KnowledgeLibraryPage() {
  return (
    <Suspense fallback={<p className="text-xs text-lcars-muted animate-pulse">Loading…</p>}>
      <KnowledgeLibraryPageInner />
    </Suspense>
  );
}

function KnowledgeLibraryPageInner() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [stats, setStats] = useState<KnowledgeLibraryStats | null>(null);
  const [documents, setDocuments] = useState<ProcessingDocument[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageErrorIsAuth, setPageErrorIsAuth] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // MSN-0334: filters/page/selected document now read from and written
  // to the URL, not just component state -- previously a reload or
  // returning later always reset to page 0 with no filters, no matter
  // how deep into a review session the Captain was. A shared link also
  // now reproduces the exact same view.
  const initialSearch = searchParams.get('q') ?? '';
  const [searchInput, setSearchInput] = useState(initialSearch);
  const [search, setSearch] = useState(initialSearch);
  const [category, setCategory] = useState(searchParams.get('category') ?? '');
  const [sensitivity, setSensitivity] = useState(searchParams.get('sensitivity') ?? '');
  const [status, setStatus] = useState(searchParams.get('status') ?? '');
  const [reviewFilter, setReviewFilter] = useState<'' | 'none' | ReviewDecision>(
    (searchParams.get('decision') as '' | 'none' | ReviewDecision) ?? '');
  const [reviewStatusFilter, setReviewStatusFilter] = useState<'' | ReviewStatus>(
    (searchParams.get('review_status') as '' | ReviewStatus) ?? '');

  // MSN-0331: 795 documents at awaiting_review made the old 50/page
  // default with no page controls a real visibility gap — only the
  // newest 50 were ever reachable without hand-editing the URL.
  const PAGE_SIZE = 100;
  const [page, setPage] = useState(() => {
    const p = Number(searchParams.get('page'));
    return Number.isFinite(p) && p >= 0 ? p : 0;
  });

  const [selectedId, setSelectedId] = useState<string | null>(searchParams.get('doc'));
  const [detail, setDetail] = useState<ProcessingDocument | null>(null);
  const [chunkPreview, setChunkPreview] = useState<ProcessingChunk[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

  // MSN-0331: batch triage — distinct from selectedId (single-document
  // detail view). A document can be checked for batch action without
  // being the one shown in the detail panel.
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [batchActing, setBatchActing] = useState(false);
  const [batchReasonFor, setBatchReasonFor] = useState<ReviewDecision | null>(null);
  const [batchReasonDraft, setBatchReasonDraft] = useState('');

  const [acting, setActing] = useState<string | null>(null);
  const [reasonFor, setReasonFor] = useState<ReviewDecision | null>(null);
  const [reasonDraft, setReasonDraft] = useState('');
  const [flash, setFlash] = useState<{ msg: string; ok: boolean } | null>(null);

  // Debounce free-text search.
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 400);
    return () => clearTimeout(t);
  }, [searchInput]);

  const loadStats = useCallback(async () => {
    try {
      setStats(await fetchJson('/api/knowledge-library/stats'));
    } catch { /* stats are a nice-to-have; loadDocuments surfaces the shared error banner */ }
  }, []);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    setPageError(null);
    setPageErrorIsAuth(false);
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (category) params.set('category', category);
      if (sensitivity) params.set('sensitivity', sensitivity);
      if (status) params.set('status', status);
      if (reviewFilter) params.set('review_decision', reviewFilter);
      if (reviewStatusFilter) params.set('review_status', reviewStatusFilter);
      params.set('limit', String(PAGE_SIZE));
      params.set('offset', String(page * PAGE_SIZE));
      const data = await fetchJson(`/api/knowledge-library/documents?${params.toString()}`);
      setDocuments(data.documents ?? []);
      setTotal(data.total ?? 0);
    } catch (e) {
      setDocuments([]);
      setTotal(0);
      setPageError(e instanceof Error ? e.message : String(e));
      setPageErrorIsAuth(e instanceof ApiAuthError);
    } finally {
      setLoading(false);
    }
  }, [search, category, sensitivity, status, reviewFilter, reviewStatusFilter, page]);

  // Any filter change invalidates the current page and the batch
  // selection (checked IDs may no longer even be in view). Skips the
  // very first render — the initial filter values themselves came from
  // the URL (MSN-0334), including a possibly-nonzero page, and this
  // effect would otherwise stomp that restored page back to 0 before
  // the Captain ever saw it.
  const isFirstFilterEffect = useRef(true);
  useEffect(() => {
    if (isFirstFilterEffect.current) { isFirstFilterEffect.current = false; return; }
    setPage(0); setCheckedIds(new Set());
  }, [search, category, sensitivity, status, reviewFilter, reviewStatusFilter]);

  // MSN-0334: mirror current view state into the URL so a reload or a
  // later return (or a shared link) reproduces exactly what the Captain
  // was looking at — filters, page, and which document was open.
  useEffect(() => {
    const params = new URLSearchParams();
    if (search) params.set('q', search);
    if (category) params.set('category', category);
    if (sensitivity) params.set('sensitivity', sensitivity);
    if (status) params.set('status', status);
    if (reviewFilter) params.set('decision', reviewFilter);
    if (reviewStatusFilter) params.set('review_status', reviewStatusFilter);
    if (page > 0) params.set('page', String(page));
    if (selectedId) params.set('doc', selectedId);
    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }, [search, category, sensitivity, status, reviewFilter, reviewStatusFilter, page, selectedId, router, pathname]);

  useEffect(() => { loadStats(); }, [loadStats]);
  useEffect(() => { loadDocuments(); }, [loadDocuments]);

  const loadDetail = useCallback(async (id: string) => {
    setDetailLoading(true);
    setDetail(null);
    setChunkPreview([]);
    setDetailError(null);
    try {
      const data = await fetchJson(`/api/knowledge-library/documents/${encodeURIComponent(id)}`);
      setDetail(data.document);
      setChunkPreview(data.chunk_preview ?? []);
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : String(e));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId) loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  const decide = useCallback(async (id: string, decision: ReviewDecision, reason?: string) => {
    setActing(id);
    try {
      const data = await fetchJson(`/api/knowledge-library/documents/${encodeURIComponent(id)}/decide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, decided_by: 'Captain', ...(reason ? { reason } : {}) }),
      });
      setFlash({ msg: `${DECISION_LABELS[decision]} recorded.`, ok: true });
      const historyEntry = {
        decision, decided_by: 'Captain', reason: reason ?? null,
        at: new Date().toISOString(), memory_document_id: data.memory_document_id ?? null,
      };
      const patch = {
        review_decision: decision,
        review_status: data.review_status as ReviewStatus,
        memory_document_id: data.memory_document_id ?? null,
      };
      setDocuments((prev) => prev.map((d) => (d.id === id
        ? { ...d, ...patch, review_history: [...(d.review_history ?? []), historyEntry] }
        : d)));
      setDetail((prev) => (prev && prev.id === id
        ? { ...prev, ...patch, review_history: [...(prev.review_history ?? []), historyEntry] }
        : prev));
      loadStats();
    } catch (e) {
      setFlash({
        msg: e instanceof ApiAuthError ? e.message : (e instanceof Error ? e.message : String(e)),
        ok: false,
      });
    } finally {
      setActing(null);
      setReasonFor(null);
      setReasonDraft('');
      setTimeout(() => setFlash(null), 4000);
    }
  }, [loadStats]);

  // MSN-0334: keyboard shortcuts for a sustained review session — every
  // decision previously required reaching for the mouse. Ignored while
  // typing in any text field (search box, reason input) so normal
  // typing (e.g. the letter "a") never misfires a decision.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
      if (!selectedId || documents.length === 0) return;

      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        const idx = documents.findIndex((d) => d.id === selectedId);
        if (idx >= 0 && idx < documents.length - 1) setSelectedId(documents[idx + 1].id);
        return;
      }
      if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        const idx = documents.findIndex((d) => d.id === selectedId);
        if (idx > 0) setSelectedId(documents[idx - 1].id);
        return;
      }

      const canDecideNow = !!detail && detail.id === selectedId && !reasonFor
        && detail.review_status !== 'resolved' && detail.review_status !== 'rejected'
        && detail.status === 'awaiting_review' && acting !== detail.id;
      if (!canDecideNow) return;

      if (e.key === 'a') { e.preventDefault(); decide(selectedId, 'approved_chunks'); }
      else if (e.key === 'm') { e.preventDefault(); decide(selectedId, 'approved_metadata'); }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [selectedId, documents, detail, reasonFor, acting, decide]);

  // MSN-0331: applies one decision to every checked document in one
  // Captain action. Reuses the same /decide semantics per-document
  // server-side (lib/knowledgeLibraryDecide.ts) — this is a throughput
  // fix, not a new decision-making path.
  const batchDecide = useCallback(async (decision: ReviewDecision, reason?: string) => {
    const ids = Array.from(checkedIds);
    if (ids.length === 0) return;
    setBatchActing(true);
    try {
      const data = await fetchJson('/api/knowledge-library/documents/batch-decide', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids, decision, decided_by: 'Captain', ...(reason ? { reason } : {}) }),
      });
      setFlash({
        msg: `${DECISION_LABELS[decision]}: ${data.succeeded}/${data.requested} succeeded${data.failed ? `, ${data.failed} failed` : ''}.`,
        ok: data.failed === 0,
      });
      setCheckedIds(new Set());
      loadDocuments();
      loadStats();
    } catch (e) {
      setFlash({
        msg: e instanceof ApiAuthError ? e.message : (e instanceof Error ? e.message : String(e)),
        ok: false,
      });
    } finally {
      setBatchActing(false);
      setBatchReasonFor(null);
      setBatchReasonDraft('');
      setTimeout(() => setFlash(null), 6000);
    }
  }, [checkedIds, loadDocuments, loadStats]);

  const toggleChecked = (id: string) => {
    setCheckedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const allVisibleChecked = documents.length > 0 && documents.every((d) => checkedIds.has(d.id));
  const toggleAllVisible = () => {
    setCheckedIds((prev) => {
      if (allVisibleChecked) {
        const next = new Set(prev);
        documents.forEach((d) => next.delete(d.id));
        return next;
      }
      const next = new Set(prev);
      documents.forEach((d) => next.add(d.id));
      return next;
    });
  };

  const clearFilters = () => {
    setSearchInput(''); setSearch(''); setCategory(''); setSensitivity('');
    setStatus(''); setReviewFilter(''); setReviewStatusFilter('');
  };

  const selectClass = 'rounded-lcars border border-edge bg-panel/40 px-3 py-1.5 text-xs text-lcars-text';

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel title="Knowledge Library" accent="science" eyebrow="USS-TJR-MSN-0205C/D — VM Processing Pipeline">
        <div className="flex flex-col gap-4">
          <div>
            <p className="mb-2 text-[10px] uppercase tracking-[0.2em] text-lcars-muted">
              Pipeline Health — system status, nothing here is yours to act on
            </p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatTile label="Total Documents" value={stats?.total_documents ?? '—'} accent="science" />
              <StatTile label="In Progress" value={stats?.in_progress ?? '—'} accent="engineering" />
              <StatTile label="OCR Required" value={stats?.ocr_required ?? '—'} accent="engineering" />
              <StatTile label="Failed" value={stats?.failed_documents ?? '—'} accent="operations" />
            </div>
          </div>
          <div>
            <p className="mb-2 text-[10px] uppercase tracking-[0.2em] text-lcars-muted">
              Your Review Queue — needs a decision from you
            </p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <StatTile label="Needs Your Review" value={stats?.needs_your_review ?? '—'} accent="command" />
              <StatTile label="Needs Follow-Up" value={stats?.needs_followup ?? '—'} accent="command" />
              <StatTile label="Approved to Memory" value={stats?.memory_approved ?? '—'} accent="medical" />
              <StatTile label="Rejected" value={stats?.rejected ?? '—'} accent="operations" />
              {/* MSN-0334: sustained-review-session progress -- previously
                  nothing showed how much ground was actually covered in a
                  session, only how much remained. */}
              <StatTile label="Reviewed Today" value={stats?.decided_today ?? '—'} accent="science" />
            </div>
          </div>
        </div>
      </LCARSPanel>

      {pageError && (
        <div className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-xs text-operations">
          {pageErrorIsAuth ? (
            <>Your session has expired. <a href="/login" className="font-semibold underline">Sign in again</a> to view the Knowledge Library.</>
          ) : (
            <>Failed to load Knowledge Library: {pageError}</>
          )}
        </div>
      )}

      <LCARSPanel
        title="Filters"
        accent="science"
        actions={(
          <button
            onClick={clearFilters}
            className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:text-science transition-colors"
          >
            Clear
          </button>
        )}
      >
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            placeholder="Search filename, summary, source…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="min-w-[220px] flex-1 rounded-lcars border border-edge bg-panel/40 px-3 py-1.5 text-xs text-lcars-text placeholder:text-lcars-muted focus:border-science/60 focus:outline-none"
          />
          <select value={category} onChange={(e) => setCategory(e.target.value)} className={selectClass}>
            <option value="">All categories</option>
            {CATEGORY_OPTIONS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={sensitivity} onChange={(e) => setSensitivity(e.target.value)} className={selectClass}>
            <option value="">All sensitivity</option>
            {SENSITIVITY_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} className={selectClass}>
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={reviewFilter} onChange={(e) => setReviewFilter(e.target.value as typeof reviewFilter)} className={selectClass}>
            <option value="">Any decision</option>
            <option value="none">Undecided (queue)</option>
            <option value="approved_metadata">Approved — metadata</option>
            <option value="approved_summary">Approved — summary</option>
            <option value="approved_chunks">Approved — chunks</option>
            <option value="rejected">Rejected</option>
            <option value="needs_review">Needs review</option>
          </select>
          <select
            value={reviewStatusFilter}
            onChange={(e) => setReviewStatusFilter(e.target.value as typeof reviewStatusFilter)}
            className={selectClass}
          >
            <option value="">Any review status</option>
            <option value="awaiting_followup">Awaiting Follow-Up</option>
            <option value="resolved">Resolved</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
      </LCARSPanel>

      <div className="flex flex-col gap-4 lg:flex-row">
        <LCARSPanel
          title={`Documents (${total})`}
          accent="science"
          className="flex-1"
          actions={total > PAGE_SIZE ? (
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-lcars-muted">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="rounded border border-edge px-2 py-1 hover:text-science disabled:opacity-30"
              >
                Prev
              </button>
              <span>
                {page * PAGE_SIZE + 1}–{Math.min(total, (page + 1) * PAGE_SIZE)} of {total}
              </span>
              <button
                onClick={() => setPage((p) => ((p + 1) * PAGE_SIZE < total ? p + 1 : p))}
                disabled={(page + 1) * PAGE_SIZE >= total}
                className="rounded border border-edge px-2 py-1 hover:text-science disabled:opacity-30"
              >
                Next
              </button>
            </div>
          ) : undefined}
        >
          {loading ? (
            <p className="text-xs text-lcars-muted animate-pulse">Loading…</p>
          ) : documents.length === 0 ? (
            <p className="text-xs text-lcars-muted">No documents match these filters.</p>
          ) : (
            <>
              <label className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-wider text-lcars-muted">
                <input type="checkbox" checked={allVisibleChecked} onChange={toggleAllVisible} />
                Select all visible ({documents.length})
              </label>
              <ul className="flex flex-col gap-2">
                {documents.map((doc) => (
                  <li key={doc.id} className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      className="mt-4"
                      checked={checkedIds.has(doc.id)}
                      onChange={() => toggleChecked(doc.id)}
                      onClick={(e) => e.stopPropagation()}
                    />
                    <button
                      onClick={() => setSelectedId(doc.id)}
                      className={`w-full rounded border p-3 text-left transition-colors ${
                        selectedId === doc.id ? 'border-science bg-science/10' : 'border-edge bg-panel-2/60 hover:border-science/40'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-xs font-medium text-lcars-text">{doc.filename}</p>
                          <p className="mt-0.5 text-[10px] text-lcars-muted">
                            {doc.source_name} · {formatBytes(doc.size_bytes)}
                          </p>
                        </div>
                        <div className="flex shrink-0 flex-col items-end gap-1">
                          <StatusBadge label={doc.status} status={doc.status} />
                          <StatusBadge label={doc.sensitivity} tone={sensitivityTone(doc.sensitivity)} />
                        </div>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        {doc.category && (
                          <span className="rounded-full border border-edge px-2 py-0.5 text-[10px] text-lcars-muted">{doc.category}</span>
                        )}
                        {doc.review_decision && (
                          <StatusBadge
                            label={DECISION_LABELS[doc.review_decision]}
                            tone={doc.review_decision === 'rejected' ? 'operations' : doc.review_decision === 'needs_review' ? 'command' : 'status'}
                          />
                        )}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </LCARSPanel>

        {checkedIds.size > 0 && (
          <LCARSPanel title={`Batch Decide (${checkedIds.size} selected)`} accent="command" className="lg:w-[340px]">
            {flash && (
              <div className={`mb-2 rounded border px-3 py-2 text-xs ${flash.ok ? 'border-status/40 bg-status/10 text-status' : 'border-operations/40 bg-operations/10 text-operations'}`}>
                {flash.msg}
              </div>
            )}
            {batchReasonFor ? (
              <div className="flex flex-col gap-2">
                <input
                  type="text"
                  placeholder={`Reason for ${DECISION_LABELS[batchReasonFor].toLowerCase()} (required)`}
                  value={batchReasonDraft}
                  onChange={(e) => setBatchReasonDraft(e.target.value)}
                  className="w-full rounded border border-edge bg-panel px-2 py-1.5 text-xs text-lcars-text placeholder:text-lcars-muted focus:border-operations/60 focus:outline-none"
                />
                <div className="flex gap-2">
                  <button
                    disabled={!batchReasonDraft.trim() || batchActing}
                    onClick={() => batchDecide(batchReasonFor, batchReasonDraft.trim())}
                    className="flex-1 rounded border border-operations/60 bg-operations/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-operations hover:bg-operations/20 disabled:opacity-40 transition-colors"
                  >
                    {batchActing ? 'Working…' : `Confirm ${DECISION_LABELS[batchReasonFor]}`}
                  </button>
                  <button
                    onClick={() => { setBatchReasonFor(null); setBatchReasonDraft(''); }}
                    className="rounded border border-edge px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-lcars-muted hover:text-lcars-text transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-1.5">
                <p className="mb-1 text-[11px] text-lcars-muted">
                  Applies one decision to all {checkedIds.size} selected documents. Each is still checked individually server-side (idempotent, terminal-status guarded) — only genuinely eligible ones are decided.
                </p>
                <button
                  disabled={batchActing}
                  onClick={() => batchDecide('approved_chunks')}
                  className="rounded border border-status/60 bg-status/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-status hover:bg-status/20 disabled:opacity-40 transition-colors"
                >
                  {batchActing ? 'Working…' : 'Approve'}
                </button>
                <button
                  disabled={batchActing}
                  onClick={() => batchDecide('approved_metadata')}
                  className="rounded border border-status/60 bg-status/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-status hover:bg-status/20 disabled:opacity-40 transition-colors"
                >
                  {DECISION_LABELS.approved_metadata}
                </button>
                <div className="mt-1 flex gap-1.5">
                  <button
                    disabled={batchActing}
                    onClick={() => setBatchReasonFor('needs_review')}
                    className="flex-1 rounded border border-command/40 bg-command/5 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-command hover:bg-command/10 disabled:opacity-40 transition-colors"
                  >
                    Needs Review
                  </button>
                  <button
                    disabled={batchActing}
                    onClick={() => setBatchReasonFor('rejected')}
                    className="flex-1 rounded border border-operations/40 bg-operations/5 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-operations hover:bg-operations/10 disabled:opacity-40 transition-colors"
                  >
                    Reject
                  </button>
                </div>
                <button
                  onClick={() => setCheckedIds(new Set())}
                  className="mt-2 text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:text-lcars-text transition-colors"
                >
                  Clear selection
                </button>
              </div>
            )}
          </LCARSPanel>
        )}

        {selectedId && (
          <LCARSPanel
            title="Document Detail"
            accent="medical"
            eyebrow="j/k or ↓/↑ next-prev · a approve · m metadata-only"
            className="lg:w-[420px]"
            actions={(
              <button
                onClick={() => { setSelectedId(null); setDetail(null); }}
                className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:text-medical transition-colors"
              >
                Close
              </button>
            )}
          >
            {detailError ? (
              <div className="rounded border border-operations/40 bg-operations/10 px-3 py-2 text-xs text-operations">
                {detailError.includes('session has expired') ? (
                  <>{detailError} <a href="/login" className="font-semibold underline">Sign in again</a>.</>
                ) : (
                  <>Failed to load document: {detailError}</>
                )}
              </div>
            ) : detailLoading || !detail ? (
              <p className="text-xs text-lcars-muted animate-pulse">Loading…</p>
            ) : (
              <div className="flex flex-col gap-3">
                <div>
                  <p className="text-sm font-semibold text-lcars-text">{detail.filename}</p>
                  <p className="mt-0.5 break-all text-[10px] text-lcars-muted">{detail.source_path}</p>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  <StatusBadge label={detail.status} status={detail.status} />
                  <StatusBadge label={detail.sensitivity} tone={sensitivityTone(detail.sensitivity)} />
                  {detail.category && <StatusBadge label={detail.category} tone="science" />}
                  {/* The status pill above always reads the processing
                      pipeline state (permanently 'awaiting_review' once a
                      document finishes processing, per migration 0043) — it
                      never reflects the review decision. memory_document_id
                      is the precise signal that this document was actually
                      approved into knowledge_documents (Command Memory), not
                      just that some decision was recorded. */}
                  {detail.memory_document_id && (
                    <StatusBadge label="Committed to Memory" tone="medical" />
                  )}
                  {detail.review_decision && !detail.memory_document_id && (
                    <StatusBadge
                      label={DECISION_LABELS[detail.review_decision]}
                      tone={detail.review_decision === 'rejected' ? 'operations' : 'command'}
                    />
                  )}
                </div>

                {(detail.sensitivity === 'sensitive' || detail.sensitivity === 'restricted') && (
                  <div className="rounded border border-operations/40 bg-operations/10 px-3 py-2 text-[11px] text-operations">
                    Flagged {detail.sensitivity} — review carefully before approving into memory.
                  </div>
                )}

                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
                  <dt className="text-lcars-muted">OCR status</dt>
                  <dd className="text-lcars-text">
                    {detail.ocr_used ? `OCR (${detail.ocr_engine ?? 'unknown engine'})` : detail.status === 'ocr_required' ? 'Required — pending' : 'Not required'}
                  </dd>
                  <dt className="text-lcars-muted">Tags</dt>
                  <dd className="text-lcars-text">{detail.tags?.length ? detail.tags.join(', ') : '—'}</dd>
                  <dt className="text-lcars-muted">Memory recommendation</dt>
                  <dd className="text-lcars-text">{detail.memory_recommendation ?? '—'}</dd>
                  <dt className="text-lcars-muted">Chunks</dt>
                  <dd className="text-lcars-text">{detail.chunk_count}</dd>
                  {/* MSN-0332: the Command Memory category this document
                      would be filed under if approved -- computed with the
                      exact same assignCategory() the approval write path
                      itself uses, so this is a genuine preview, not a
                      guess. Shown before the Captain decides, not just
                      after. */}
                  <dt className="text-lcars-muted">Memory category (if approved)</dt>
                  <dd className="text-lcars-text">{assignCategory('Personal Archive', detail.category ?? null)}</dd>
                  {/* MSN-0332 audit finding: no source-document-date field
                      exists anywhere in this pipeline's schema (only
                      processing timestamps) -- disclosed here rather than
                      silently omitted, so it reads as "not tracked", not
                      as a UI bug. */}
                  <dt className="text-lcars-muted">Document date</dt>
                  <dd className="text-lcars-text">Not tracked by this pipeline</dd>
                </dl>

                {detail.summary && (
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Summary</p>
                    <p className="mt-1 text-xs text-lcars-text">{detail.summary}</p>
                  </div>
                )}

                {detail.failure_reason && (
                  <div className="rounded border border-operations/40 bg-operations/10 px-3 py-2 text-[11px] text-operations">
                    Failed: {detail.failure_reason}
                  </div>
                )}

                {chunkPreview.length > 0 && (
                  <details className="text-xs">
                    <summary className="cursor-pointer text-[10px] uppercase tracking-[0.2em] text-lcars-muted">
                      Chunk preview ({chunkPreview.length} of {detail.chunk_count})
                    </summary>
                    <ul className="mt-2 flex flex-col gap-2">
                      {chunkPreview.map((c) => (
                        <li key={c.id} className="rounded border border-edge bg-panel-2/60 p-2 text-[11px] text-lcars-muted">
                          #{c.chunk_index}: {c.chunk_text.slice(0, 160)}{c.chunk_text.length > 160 ? '…' : ''}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}

                {flash && (
                  <div className={`rounded border px-3 py-2 text-xs ${flash.ok ? 'border-status/40 bg-status/10 text-status' : 'border-operations/40 bg-operations/10 text-operations'}`}>
                    {flash.msg}
                  </div>
                )}

                {/* USS-TJR-MSN-0206J-1: only 'resolved'/'rejected' are terminal.
                    'awaiting_followup' (a prior 'needs_review' decision) falls
                    through to the decision buttons below instead of dead-ending
                    here — this is the fix for the real deadlock migration 0047
                    resolved (3 documents were permanently stuck before it). */}
                {detail.review_status === 'resolved' || detail.review_status === 'rejected' ? (
                  <div className="rounded border border-edge bg-panel-2/60 px-3 py-2 text-[11px] text-lcars-muted">
                    {REVIEW_STATUS_LABELS[detail.review_status]}: {detail.review_decision ? DECISION_LABELS[detail.review_decision] : '—'}
                    {detail.review_decided_by ? ` by ${detail.review_decided_by}` : ''}
                    {detail.review_reason ? ` — "${detail.review_reason}"` : ''}
                  </div>
                ) : detail.status !== 'awaiting_review' ? (
                  <p className="text-[11px] text-lcars-muted">
                    Not yet ready for review — still in the processing pipeline ({detail.status}).
                  </p>
                ) : reasonFor ? (
                  <div className="flex flex-col gap-2">
                    <input
                      type="text"
                      placeholder={`Reason for ${DECISION_LABELS[reasonFor].toLowerCase()} (required)`}
                      value={reasonDraft}
                      onChange={(e) => setReasonDraft(e.target.value)}
                      className="w-full rounded border border-edge bg-panel px-2 py-1.5 text-xs text-lcars-text placeholder:text-lcars-muted focus:border-operations/60 focus:outline-none"
                    />
                    <div className="flex gap-2">
                      <button
                        disabled={!reasonDraft.trim() || acting === detail.id}
                        onClick={() => decide(detail.id, reasonFor, reasonDraft.trim())}
                        className="flex-1 rounded border border-operations/60 bg-operations/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-operations hover:bg-operations/20 disabled:opacity-40 transition-colors"
                      >
                        {acting === detail.id ? 'Working…' : `Confirm ${DECISION_LABELS[reasonFor]}`}
                      </button>
                      <button
                        onClick={() => { setReasonFor(null); setReasonDraft(''); }}
                        className="rounded border border-edge px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-lcars-muted hover:text-lcars-text transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col gap-1.5">
                    {detail.review_status === 'awaiting_followup' && (
                      <div className="rounded border border-command/40 bg-command/10 px-3 py-2 text-[11px] text-command">
                        Awaiting follow-up — previously marked &ldquo;Needs Review&rdquo;
                        {detail.review_reason ? `: "${detail.review_reason}"` : ''}. Choose a decision below to resolve it.
                      </div>
                    )}
                    {/* MSN-0332: what actually gets written, before the
                        Captain clicks anything — the mission's own
                        "what will be written if approved" requirement. */}
                    <p className="mb-1 text-[10px] text-lcars-muted">
                      Approve writes {detail.summary ? 'the summary above' : `a metadata-only stub ("${detail.filename}")`} as
                      the memory content, plus full chunk/embedding copy either way — same searchable content regardless of
                      which Approve button, only the readable text differs. Approve — Metadata Only always uses the stub,
                      even if a summary exists.
                    </p>
                    {/* Only 2 buttons: approved_summary is deliberately not
                        offered here anymore — since chunk-copying now
                        happens for every approve tier (see decide/route.ts),
                        it became functionally identical to approved_chunks.
                        Still kept in ReviewDecision/DECISION_LABELS/the
                        review-decision filter below so the 5 documents
                        already decided that way stay correctly labelled and
                        filterable. */}
                    <button
                      disabled={acting === detail.id}
                      onClick={() => decide(detail.id, 'approved_chunks')}
                      className="rounded border border-status/60 bg-status/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-status hover:bg-status/20 disabled:opacity-40 transition-colors"
                    >
                      Approve
                    </button>
                    <button
                      disabled={acting === detail.id}
                      onClick={() => decide(detail.id, 'approved_metadata')}
                      className="rounded border border-status/60 bg-status/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-status hover:bg-status/20 disabled:opacity-40 transition-colors"
                    >
                      {DECISION_LABELS.approved_metadata}
                    </button>
                    <div className="mt-1 flex gap-1.5">
                      <button
                        disabled={acting === detail.id}
                        onClick={() => setReasonFor('needs_review')}
                        className="flex-1 rounded border border-command/40 bg-command/5 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-command hover:bg-command/10 disabled:opacity-40 transition-colors"
                      >
                        Needs Review
                      </button>
                      <button
                        disabled={acting === detail.id}
                        onClick={() => setReasonFor('rejected')}
                        className="flex-1 rounded border border-operations/40 bg-operations/5 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-operations hover:bg-operations/10 disabled:opacity-40 transition-colors"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                )}

                {detail.review_history && detail.review_history.length > 0 && (
                  <details className="text-xs">
                    <summary className="cursor-pointer text-[10px] uppercase tracking-[0.2em] text-lcars-muted">
                      Review history ({detail.review_history.length})
                    </summary>
                    <ul className="mt-2 flex flex-col gap-1.5">
                      {detail.review_history.map((h, i) => (
                        <li key={i} className="rounded border border-edge bg-panel-2/60 p-2 text-[11px] text-lcars-muted">
                          {DECISION_LABELS[h.decision]} by {h.decided_by} — {new Date(h.at).toLocaleString()}
                          {h.reason ? ` — "${h.reason}"` : ''}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            )}
          </LCARSPanel>
        )}
      </div>
    </div>
  );
}
