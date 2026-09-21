import type { EvidenceContract } from '@/lib/designContracts';

export function EvidenceMeta({
  source,
  observedAt,
  confidence,
  state,
}: {
  source?: string | null;
  observedAt?: string | null;
  confidence?: string | null;
  state?: EvidenceContract['state'];
}) {
  const parts = [
    source ? `Source: ${source}` : null,
    observedAt ? `Observed: ${new Date(observedAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}` : null,
    confidence ? `Confidence: ${confidence}` : null,
    state ? `State: ${state.replace('-', ' ')}` : null,
  ].filter(Boolean);
  if (!parts.length) return null;
  return <p className="text-[10.5px] leading-relaxed text-wb-ink2" aria-label="Evidence metadata">{parts.join(' · ')}</p>;
}
