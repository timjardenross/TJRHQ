import { evidenceSegments, normaliseEvidence, normaliseRisk, riskTone, type HqEvidence, type HqRisk } from '@/lib/hq/vocab';

/** Filled pill. Colour here always means risk, nothing else. */
export function RiskPill({ risk }: { risk: HqRisk | string | null }) {
  const r = typeof risk === 'string' && !['High', 'Medium', 'Low'].includes(risk) ? normaliseRisk(risk) : (risk as HqRisk | null);
  if (!r) return null;
  return <span className={`hq-pill ${riskTone(r)}`}>Risk: {r}</span>;
}

/** Neutral outlined bar. Evidence quality never uses a risk colour. */
export function EvidenceBar({ evidence }: { evidence: HqEvidence | string | number | null }) {
  const e = normaliseEvidence(evidence as string | number | null);
  if (e === 'Unknown') return null;
  const n = evidenceSegments(e);
  return (
    <span className="hq-ev" title="How well supported this is. Separate from risk.">
      Evidence
      {[0, 1, 2].map((i) => <i key={i} className={i < n ? 'on' : ''} />)}
      {e}
    </span>
  );
}

export function Notice({ children }: { children: React.ReactNode }) {
  return <div className="hq-notice" role="note">{children}</div>;
}

export function Loading({ what }: { what: string }) {
  return <div className="hq-quiet" role="status">Loading {what}…</div>;
}

export function ErrorLine({ what, detail }: { what: string; detail?: string | null }) {
  return <div className="hq-notice" role="alert">Could not load {what}.{detail ? ` ${detail}` : ''} Existing workbenches are unaffected.</div>;
}
