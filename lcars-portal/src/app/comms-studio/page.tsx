'use client';

// EOS Phase 2 Priority 5 (Executive Communications Studio): assembles a
// document directly from canonical platform data (lib/commsStudio.ts —
// Captain Intelligence, the Decide ledger, Missions), lets the Captain
// review and edit it, then saves it into the existing comms_content
// pipeline as a draft. It never generates prose from scratch and never
// publishes anything itself — publishing is /comms's existing, now-
// governed advance flow (api/comms/[id]/advance/route.ts).
//
// Lives outside the (app) route group deliberately, same zero-nav,
// contextual-entry pattern as /decide, /ask, /home, /recommended,
// /investigate (docs/EOS-CANONICAL-ARCHITECTURE-DECISIONS.md §5) — reached
// from Home's quiet footer link, not a browsable menu item.
//
// Disclosed scope for this delivery: only three document types are wired
// (Executive Brief, Decision Brief, Mission Report) — SitRep, Stakeholder
// Update, Board Papers, and Talking Points are not implemented. The
// assembly architecture (assembleStudioDraft in lib/commsStudio.ts)
// supports adding more without touching this page or the save route; see
// the mission report for what's left.

import { useState } from 'react';
import Link from 'next/link';
import { assembleStudioDraft, type StudioAssembly, type StudioDocType } from '@/lib/commsStudio';

const DOC_TYPES: { key: StudioDocType; label: string; needsRef: boolean; refLabel: string }[] = [
  { key: 'executive_brief', label: 'Executive Brief', needsRef: false, refLabel: '' },
  { key: 'decision_brief', label: 'Decision Brief', needsRef: true, refLabel: 'Decide ledger ID' },
  { key: 'mission_report', label: 'Mission Report', needsRef: true, refLabel: 'Mission ID (e.g. USS-TJR-MSN-0123)' },
];

export default function CommsStudioPage() {
  const [type, setType] = useState<StudioDocType>('executive_brief');
  const [refId, setRefId] = useState('');
  const [draft, setDraft] = useState<StudioAssembly | null>(null);
  const [editBody, setEditBody] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);

  const active = DOC_TYPES.find((d) => d.key === type)!;

  async function generate() {
    setLoading(true);
    setError(null);
    setDraft(null);
    setSavedId(null);
    const result = await assembleStudioDraft(type, refId.trim());
    setLoading(false);
    if (!result) {
      setError('Could not assemble this document — check the reference and try again.');
      return;
    }
    setDraft(result);
    setEditBody(result.body);
  }

  async function saveDraft() {
    if (!draft) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/comms-studio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, refId: refId.trim(), title: draft.title, body: editBody, evidence: draft.evidence }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error ?? 'Failed to save draft');
      setSavedId(d.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save draft');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex justify-center bg-[#0B1017] text-[#E8EDF2]">
      <div className="w-full max-w-[680px] px-7 pt-10 pb-14 flex flex-col min-h-screen">
        <Link href="/home" className="text-sm text-[#5A6875] hover:text-[#93A1B0] mb-8 inline-flex items-center gap-1.5 w-fit">
          ← Home
        </Link>

        <h1 className="text-[20px] font-semibold mb-1">Communications Studio</h1>
        <p className="text-[13.5px] text-[#5A6875] mb-8 leading-relaxed">
          Assembles a document directly from canonical platform data — no invented content, every
          claim traces to a real source. Review and edit before submitting for publish approval.
        </p>

        <div className="flex flex-col gap-4 mb-6">
          <div className="flex flex-wrap gap-2">
            {DOC_TYPES.map((d) => (
              <button
                key={d.key}
                type="button"
                onClick={() => {
                  setType(d.key);
                  setDraft(null);
                  setSavedId(null);
                  setRefId('');
                }}
                className={`text-xs px-3 py-1.5 rounded border transition-colors ${
                  type === d.key
                    ? 'border-[#5AA0D8] text-[#5AA0D8] bg-[#5AA0D8]/10'
                    : 'border-[rgba(147,161,176,0.25)] text-[#93A1B0]'
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>

          {active.needsRef && (
            <input
              value={refId}
              onChange={(e) => setRefId(e.target.value)}
              placeholder={active.refLabel}
              className="rounded border border-[rgba(147,161,176,0.25)] bg-transparent px-3 py-2 text-sm text-[#E8EDF2] placeholder:text-[#5A6875]"
            />
          )}

          <button
            type="button"
            onClick={generate}
            disabled={loading || (active.needsRef && !refId.trim())}
            className="self-start rounded border border-[#5AA0D8]/50 px-4 py-2 text-xs uppercase tracking-widest text-[#5AA0D8] hover:bg-[#5AA0D8]/10 disabled:opacity-40"
          >
            {loading ? 'Assembling…' : 'Assemble Draft'}
          </button>
        </div>

        {error && <p className="text-sm text-[#D8825A] mb-4">{error}</p>}

        {draft && (
          <div className="flex flex-col gap-3">
            <p className="text-[15px] font-medium">{draft.title}</p>
            <textarea
              value={editBody}
              onChange={(e) => setEditBody(e.target.value)}
              rows={16}
              className="w-full rounded border border-[rgba(147,161,176,0.25)] bg-[#101722] px-3 py-2 text-xs font-mono leading-relaxed text-[#E8EDF2]"
            />
            {draft.evidence.length > 0 && (
              <details className="text-[12px] text-[#5A6875]">
                <summary className="cursor-pointer hover:text-[#93A1B0]">Evidence ({draft.evidence.length})</summary>
                <ul className="mt-2 flex flex-col gap-1">
                  {draft.evidence.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </details>
            )}
            {savedId ? (
              <p className="text-sm text-[#5AA0D8]">
                Saved as a draft. Continue reviewing it in{' '}
                <Link href="/comms" className="underline underline-offset-2">
                  Communications Pipeline
                </Link>{' '}
                — it still needs to move through review and your explicit publish approval before
                anyone sees it.
              </p>
            ) : (
              <button
                type="button"
                onClick={saveDraft}
                disabled={loading}
                className="self-start rounded border border-[#5AA0D8]/50 px-4 py-2 text-xs uppercase tracking-widest text-[#5AA0D8] hover:bg-[#5AA0D8]/10 disabled:opacity-40"
              >
                Save as Draft
              </button>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
