export function EvidenceMeta({
  source,
  observedAt,
  confidence,
}: {
  source?: string | null;
  observedAt?: string | null;
  confidence?: string | null;
}) {
  const parts = [
    source ? `Source: ${source}` : null,
    observedAt ? `Observed: ${new Date(observedAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}` : null,
    confidence ? `Confidence: ${confidence}` : null,
  ].filter(Boolean);
  if (!parts.length) return null;
  return <p className="text-[10.5px] leading-relaxed text-wb-ink2" aria-label="Evidence metadata">{parts.join(' · ')}</p>;
}
