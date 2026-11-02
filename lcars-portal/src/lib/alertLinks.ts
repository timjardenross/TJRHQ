/**
 * BOM warnings keep their product page in raw_text (the last http line), not in
 * canonical_url: that column is unique across sources and BOM's links are shared by
 * neighbouring states. This recovers it for display so a BOM card can link to the
 * official warning like every other card. Mirrors core/platform/alert_email.official_links.
 */
export function bomProductLink(sourceKey: string, rawText: string | null): string | null {
  if (!sourceKey.startsWith('bom_') || !rawText) return null;
  const line = rawText
    .split('\n')
    .map((l) => l.trim())
    .reverse()
    .find((l) => l.startsWith('http'));
  return line ? line.replace(/^https?:\/\/reg\.bom\.gov\.au\//, 'https://www.bom.gov.au/') : null;
}
