/**
 * Display-only tidying of an alert headline for cards. The stored headline is
 * never changed and the detail panel still shows it in full.
 *
 *  - WA DFES headlines carry the place, shire, region and dispatch ID in one
 *    parenthesis: "BUSHFIRE (LAKE ARGYLE, SHIRE OF WYNDHAM-EAST KIMBERLEY,
 *    KIMBERLEY, CAD-ID: 828476)". Split into a short title and a subtitle, and
 *    leave the ID for the detail panel.
 *  - A headline with no lowercase letters (several feeds send all caps) is
 *    title-cased so it reads as a sentence, not a shout.
 */

export interface DisplayHeadline {
  title: string;
  subtitle: string | null;
}

const SMALL_WORDS = new Set(['of', 'and', 'the', 'at', 'on', 'in', 'to', 'for']);

export function tidyCase(text: string): string {
  if (/[a-z]/.test(text) || !/[A-Z]/.test(text)) return text;
  let first = true;
  return text.toLowerCase().replace(/[a-z][a-z']*/g, (word) => {
    const keepLower = !first && SMALL_WORDS.has(word);
    first = false;
    return keepLower ? word : word[0].toUpperCase() + word.slice(1);
  });
}

export function displayHeadline(headline: string): DisplayHeadline {
  const match = /^(.*?)\s*\((.*)\)\s*$/.exec(headline);
  if (match && /CAD-ID/i.test(match[2])) {
    const kind = tidyCase(match[1].trim());
    const parts = match[2]
      .split(',')
      .map((p) => p.trim())
      .filter((p) => p && !/^CAD-ID/i.test(p));
    if (parts.length > 0) {
      const [place, ...rest] = parts;
      return { title: `${kind} — ${tidyCase(place)}`, subtitle: rest.length > 0 ? rest.map(tidyCase).join(' · ') : null };
    }
  }
  return { title: tidyCase(headline), subtitle: null };
}
