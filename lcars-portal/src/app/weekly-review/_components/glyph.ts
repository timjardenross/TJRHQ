import type { DeltaGlyph } from '@/lib/weeklyReview';

export const GLYPH_SYMBOL: Record<DeltaGlyph, string> = {
  down: '↓', flat: '→', up: '↑', warn: '⚠', ok: '✓',
};

export const GLYPH_CLASS: Record<DeltaGlyph, string> = {
  down: 'text-wb-warn-on', flat: 'text-wb-ink2', up: 'text-wb-ok-on', warn: 'text-wb-warn-on', ok: 'text-wb-ok-on',
};
