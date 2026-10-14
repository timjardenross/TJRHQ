// Parsing and speech helpers for the Captain's daily brief text (captains_daily_briefs.brief_text).
//
// brief_text is Telegram HTML. captains_brief.py escapes the dynamic text in it (&amp; &lt; &gt;)
// so a stored event containing something like "<NRP>" cannot break the Telegram send, so the tags
// are stripped here and the entities are decoded AFTER stripping. Order matters: decoding first
// would turn an escaped "&lt;NRP&gt;" into "<NRP>" and the tag stripper would then delete it.
// The result is only ever rendered as text (React escapes it) or spoken, never as raw HTML.
// Briefs stored before the escaping change contain no entities and decode to themselves.

/** Decode the three entities captains_brief.py produces. `&amp;` goes last so "&amp;lt;" -> "&lt;". */
export function decodeBriefEntities(text: string): string {
  return text.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}

// brief_text is Telegram HTML (captains_brief.py builds it for direct bot
// delivery — whole-line "<b>SECTION HEADER</b>" for section titles,
// "<i>...</i>" for the stardate line and footer signature, plain text
// paragraphs in between, sections separated by blank lines). Original
// stripHtml() below stripped tags AND collapsed every run of whitespace
// (including all newlines) into one space — safe from a raw-HTML-
// injection angle, but destroyed 100% of that structure into one run-on
// paragraph, which is what made this "hard to read." Parsed line-by-line
// instead so headers/subtitle/paragraph breaks survive, still never
// dangerouslySetInnerHTML — every tag is matched and stripped explicitly,
// nothing is ever rendered as raw HTML.
export type BriefLine =
  | { type: 'header'; text: string }
  | { type: 'subtitle'; text: string }
  | { type: 'blank' }
  | { type: 'text'; text: string };

function stripInlineTags(text: string): string {
  return decodeBriefEntities(text.replace(/<[^>]+>/g, '')).trim();
}

export function parseBriefText(raw: string): BriefLine[] {
  return raw.split('\n').map((line): BriefLine => {
    const trimmed = line.trim();
    if (trimmed === '') return { type: 'blank' };
    const headerMatch = trimmed.match(/^<b>(.*)<\/b>$/);
    if (headerMatch) return { type: 'header', text: stripInlineTags(headerMatch[1]) };
    const subtitleMatch = trimmed.match(/^<i>(.*)<\/i>$/);
    if (subtitleMatch) return { type: 'subtitle', text: stripInlineTags(subtitleMatch[1]) };
    return { type: 'text', text: stripInlineTags(trimmed) };
  });
}

// Emoji ranges covering the ones captains_brief.py actually uses (☀️⚡🌐🤖
// etc. — Misc Symbols/Dingbats/Transport/Supplemental Symbols blocks plus
// the variation-selector byte that rides along with some of them) — not
// exhaustive of every Unicode emoji ever defined, but real section-header
// decoration, not content, so stripping them loses nothing when spoken.
const EMOJI_PATTERN = /[\u{2600}-\u{27BF}\u{1F300}-\u{1FAFF}\u{2B00}-\u{2BFF}️]/gu;

// Flat, spoken-friendly text for TTS — unlike parseBriefText (which keeps
// line structure for on-screen display), speech doesn't need visual
// paragraph breaks, just tags stripped and whitespace normalized. Emojis
// stripped too — Google Cloud TTS otherwise tries to read them out
// ("sun emoji," etc.), which is just noise spoken aloud.
export function toSpokenText(raw: string): string {
  return decodeBriefEntities(raw.replace(/<[^>]+>/g, ' '))
    .replace(EMOJI_PATTERN, '')
    .replace(/\s+/g, ' ')
    .trim();
}

