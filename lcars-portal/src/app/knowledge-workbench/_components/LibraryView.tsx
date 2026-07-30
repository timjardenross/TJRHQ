'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { Card } from '@/components/ui/Card';
import { StatusBadge } from '@/components/StatusBadge';
import { assignCategory } from '@/lib/categoryPropagation';
import { fetchJson, ApiAuthError } from '@/lib/knowledgeLibraryClient';
import { DECISION_LABELS, sensitivityTone, formatBytes } from './badges';
import { DocumentDetail } from './DocumentDetail';
import { BatchTriageBar } from './BatchTriageBar';
import type {
  ProcessingDocument,
  ProcessingChunk,
  DocumentCategory,
  DocumentSensitivity,
  ProcessingStatus,
  ReviewDecision,
  ReviewStatus,
} from '@/lib/types';

const CATEGORY_OPTIONS: DocumentCategory[] = [
  'Financial', 'Legal', 'Health', 'Correspondence', 'Reference',
  'Identity', 'Property', 'Photo', 'Administrative', 'Other',
];
const SENSITIVITY_OPTIONS: DocumentSensitivity[] = ['standard', 'sensitive', 'restricted'];
const STATUS_OPTIONS: ProcessingStatus[] = [
  'received', 'extracted', 'ocr_required', 'ocr_complete',
  'classified', 'summarised', 'embedded', 'failed', 'awaiting_review', 'excluded',
];

// MSN-0334: useSearchParams() requires a Suspense boundary in the App Router
export function LibraryView() {
  return (
    <Suspense fallback={<p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>}>
      <LibraryViewInner />
    </Suspense>
  );
}

function LibraryViewInner() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [documents, setDocuments] = useState<ProcessingDocument[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageErrorIsAuth, setPageErrorIsAuth] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // MSN-0334: filters/page/selected document read from and written to URL
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

  const PAGE_SIZE = 100;
  const [page, setPage] = useState(() => {
    const p = Number(searchParams.get('page'));
    return Number.isFinite(p) && p >= 0 ? p : 0;
  });

  const [selectedId, setSelectedId] = useState<string | null>(searchParams.get('doc'));
  const [detail, setDetail] = useState<ProcessingDocument | null>(null);
  const [chunkPreview, setChunkPreview] = useState<ProcessingChunk[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

  // MSN-0331: batch triage
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [batchActing, setBatchActing] = useState(false);
  const [batchReasonFor, setBatchReasonFor] = useState<ReviewDecision | null>(null);
  const [batchReasonDraft, setBatchReasonDraft] = useState('');

  const [acting, setActing] = useState<string | null>(null);
  const [reasonFor, setReasonFor] = useState<ReviewDecision | null>(null);
  const [reasonDraft, setReasonDraft] = useState('');
  const [flash, setFlash] = useState<{ msg: string; ok: boolean } | null>(null);

  // Debounce free-text search
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 400);
    return () => clearTimeout(t);
  }, [searchInput]);

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

  // Any filter change resets page and batch selection
  const isFirstFilterEffect = useRef(true);
  useEffect(() => {
    if (isFirstFilterEffect.current) { isFirstFilterEffect.current = false; return; }
    setPage(0); setCheckedIds(new Set());
  }, [search, category, sensitivity, status, reviewFilter, reviewStatusFilter]);

  // MSN-0334: mirror current view state into URL
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
      loadDocuments();
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
  }, [loadDocuments]);

  // MSN-0334: keyboard shortcuts for sustained review sessions
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

  // MSN-0331: batch decide
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
  }, [checkedIds, loadDocuments]);

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

  const selectClass = 'rounded-lg border border-wb-line bg-wb-surface/40 px-3 py-1.5 text-xs text-wb-ink';

  return (
    <div className="flex flex-col gap-4">
      {pageError && (
        <div className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 px-4 py-3 text-xs text-wb-crit-on">
          {pageErrorIsAuth ? (
            <>Your session has expired. <a href="/login" className="font-semibold underline">Sign in again</a> to view the Knowledge Library.</>
          ) : (
            <>Failed to load Knowledge Library: {pageError}</>
          )}
        </div>
      )}

      <Card className="mb-4 p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-serif text-[14px] uppercase tracking-wide text-wb-ink">Filters</h3>
          <button
            onClick={clearFilters}
            className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2 hover:text-wb-sage-deep transition-colors"
          >
            Clear
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            placeholder="Search filename, summary, source…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="min-w-[220px] flex-1 rounded-lg border border-wb-line bg-wb-surface/40 px-3 py-1.5 text-xs text-wb-ink placeholder:text-wb-ink2 focus:border-wb-sage-deep/60 focus:outline-none"
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
      </Card>

      <div className="flex flex-col gap-4 lg:flex-row">
        <Card className="flex-1 p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-serif text-[14px] uppercase tracking-wide text-wb-ink">
              Documents ({total})
            </h3>
            {total > PAGE_SIZE && (
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-wb-ink2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="rounded border border-wb-line px-2 py-1 hover:text-wb-sage-deep disabled:opacity-30"
                >
                  Prev
                </button>
                <span>
                  {page * PAGE_SIZE + 1}–{Math.min(total, (page + 1) * PAGE_SIZE)} of {total}
                </span>
                <button
                  onClick={() => setPage((p) => ((p + 1) * PAGE_SIZE < total ? p + 1 : p))}
                  disabled={(page + 1) * PAGE_SIZE >= total}
                  className="rounded border border-wb-line px-2 py-1 hover:text-wb-sage-deep disabled:opacity-30"
                >
                  Next
                </button>
              </div>
            )}
          </div>
          {loading ? (
            <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
          ) : documents.length === 0 ? (
            <p className="text-xs text-wb-ink2">No documents match these filters.</p>
          ) : (
            <>
              <label className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-wider text-wb-ink2">
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
                        selectedId === doc.id ? 'border-wb-sage-deep bg-wb-sage/10' : 'border-wb-line bg-wb-surface-2/60 hover:border-wb-sage-deep/40'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-xs font-medium text-wb-ink">{doc.filename}</p>
                          <p className="mt-0.5 text-[10px] text-wb-ink2">
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
                          <span className="rounded-full border border-wb-line px-2 py-0.5 text-[10px] text-wb-ink2">{doc.category}</span>
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
        </Card>

        <BatchTriageBar
          checkedIds={checkedIds}
          batchActing={batchActing}
          batchReasonFor={batchReasonFor}
          batchReasonDraft={batchReasonDraft}
          setBatchReasonFor={setBatchReasonFor}
          setBatchReasonDraft={setBatchReasonDraft}
          batchDecide={batchDecide}
          setCheckedIds={setCheckedIds}
          flash={flash}
        />

        <DocumentDetail
          selectedId={selectedId}
          detail={detail}
          chunkPreview={chunkPreview}
          detailLoading={detailLoading}
          detailError={detailError}
          reasonFor={reasonFor}
          reasonDraft={reasonDraft}
          acting={acting}
          flash={flash}
          onClose={() => {
            setSelectedId(null);
            setDetail(null);
          }}
          onSetReasonFor={setReasonFor}
          onSetReasonDraft={setReasonDraft}
          onDecide={decide}
        />
      </div>
    </div>
  );
}
