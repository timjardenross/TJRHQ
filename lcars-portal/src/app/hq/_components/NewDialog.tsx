'use client';

// The contextual New action: capture, research, ask, or mission, from any HQ
// screen, with whatever the user is looking at attached.
import { useEffect, useRef, useState } from 'react';
import { useHq } from '@/lib/hq/HqProvider';
import { trapTab } from '@/lib/hq/focusTrap';
import { ASK_AVAILABLE, RESEARCH_RUNNER_CONNECTED, hqCapture, hqMission, hqResearch } from '@/lib/hq/actions';

type Kind = 'capture' | 'research' | 'ask' | 'mission';

const COPY: Record<Kind, { choice: string; label: string; button: string; placeholder: string }> = {
  capture: { choice: 'Capture an idea', label: 'Idea or note', button: 'Capture', placeholder: 'e.g. Check whether other vendors use the same provider' },
  research: { choice: 'Request research', label: 'What should HQ find out?', button: 'Capture research request', placeholder: 'e.g. Which of our vendors depend on this provider?' },
  ask: { choice: 'Ask a question', label: 'Your question', button: 'Ask', placeholder: 'Ask about anything HQ knows' },
  mission: { choice: 'New mission', label: 'What needs to be done?', button: 'Create mission', placeholder: 'e.g. Review vendor contracts for settlement clauses' },
};

export function NewDialog() {
  const { newOpen, newPreset, closeNew, context, toast } = useHq();
  const [kind, setKind] = useState<Kind>('capture');
  const [text, setText] = useState('');
  const [attach, setAttach] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const areaRef = useRef<HTMLTextAreaElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!newOpen) return;
    returnTo.current = document.activeElement as HTMLElement | null;
    setKind(newPreset?.type ?? 'capture');
    setText(newPreset?.text ?? '');
    setAttach(true);
    setError(null);
    setBusy(false);
    const t = setTimeout(() => areaRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [newOpen, newPreset]);

  useEffect(() => {
    if (!newOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeNew();
      else trapTab(e, sheetRef.current, document.activeElement);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [newOpen, closeNew]);

  useEffect(() => {
    if (!newOpen && returnTo.current) { returnTo.current.focus?.(); returnTo.current = null; }
  }, [newOpen]);

  if (!newOpen) return null;
  const ctx = attach ? (newPreset?.context !== undefined ? newPreset.context : context) : null;
  const askBlocked = kind === 'ask' && !ASK_AVAILABLE;
  const c = COPY[kind];

  async function submit() {
    const body = text.trim();
    if (!body) { areaRef.current?.focus(); return; }
    if (askBlocked || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (kind === 'capture') {
        const r = await hqCapture(body, ctx);
        if (!r.ok) throw new Error(r.error ?? 'Capture failed.');
        toast(`Captured${ctx ? `, linked to “${ctx.label}”` : ''}. It is waiting to be sorted in Capture.`);
      } else if (kind === 'research') {
        const r = await hqResearch(body, ctx);
        if (!r.ok) throw new Error(r.error ?? 'Could not file the request.');
        toast(`Research request captured. ${RESEARCH_RUNNER_CONNECTED ? 'It is queued to run.' : 'Nothing is running: it waits for review in Capture.'}`);
      } else if (kind === 'mission') {
        const r = await hqMission(body, ctx);
        if (!r.ok) {
          if (r.partial) { toast(`${r.error} Your idea is saved in Capture.`); }
          else throw new Error(r.error ?? 'Could not create the mission.');
        } else {
          toast(`Mission candidate created${ctx ? ' with the source attached' : ''}. It needs your review in Missions.`);
        }
      }
      closeNew();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
      setBusy(false);
    }
  }

  return (
    <div className="hq-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) closeNew(); }}>
      <div className="hq-sheet" ref={sheetRef} role="dialog" aria-modal="true" aria-labelledby="hq-new-title">
        <h2 id="hq-new-title" style={{ fontSize: '1.05rem' }}>New</h2>
        <div className="hq-seg" role="radiogroup" aria-label="What do you want to do?">
          {(Object.keys(COPY) as Kind[]).map((k) => (
            <label key={k}>
              <input type="radio" name="hq-new-kind" value={k} checked={kind === k} onChange={() => { setKind(k); setError(null); }} />
              <span>{COPY[k].choice}</span>
            </label>
          ))}
        </div>
        {ctx && (
          <div>
            <span className="hq-ctx">From: {ctx.label}{' '}
              <button type="button" className="hq-link inline" onClick={() => setAttach(false)} aria-label="Remove attached item">remove</button>
            </span>
          </div>
        )}
        {askBlocked && <div className="hq-notice" role="note">Ask is not connected yet. Use Capture or Request research for now.</div>}
        {kind === 'research' && !RESEARCH_RUNNER_CONNECTED && (
          <div className="hq-notice" role="note">This captures a request in Capture for review. It does not start any research: no research runner is connected yet.</div>
        )}
        <label htmlFor="hq-new-text" className="hq-muted" style={{ fontSize: '.84rem' }}>{c.label}</label>
        <textarea id="hq-new-text" ref={areaRef} className="hq-input" value={text} placeholder={c.placeholder} onChange={(e) => setText(e.target.value)} disabled={askBlocked} />
        {error && <div className="hq-notice" role="alert">{error}</div>}
        <div className="hq-acts">
          <button type="button" className="hq-btn primary" onClick={submit} disabled={busy || askBlocked} aria-disabled={busy || askBlocked}>{busy ? 'Working…' : c.button}</button>
          <button type="button" className="hq-btn quiet" onClick={closeNew}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
