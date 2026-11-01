import { describe, it, expect } from 'vitest';
import { decodeBriefEntities, parseBriefText, toSpokenText } from '../briefText';

describe('decodeBriefEntities', () => {
  it('decodes the three entities captains_brief.py produces', () => {
    expect(decodeBriefEntities('&lt;NRP&gt; &amp; &lt;ORGANIZATION&gt;')).toBe('<NRP> & <ORGANIZATION>');
  });
  it('decodes &amp; last, so an escaped entity stays an entity', () => {
    expect(decodeBriefEntities('&amp;lt;')).toBe('&lt;');
    expect(decodeBriefEntities('&amp;amp;')).toBe('&amp;');
  });
  it('leaves plain text, and briefs stored before escaping existed, unchanged', () => {
    expect(decodeBriefEntities('Plain text, nothing special.')).toBe('Plain text, nothing special.');
    expect(decodeBriefEntities('AT&T results beat R&D forecasts')).toBe('AT&T results beat R&D forecasts');
  });
});

describe('parseBriefText', () => {
  it('shows escaped placeholders and ampersands as the text they were', () => {
    const lines = parseBriefText('  1. Sanctions regarding &lt;NRP&gt; imports &amp; more');
    expect(lines).toEqual([{ type: 'text', text: '1. Sanctions regarding <NRP> imports & more' }]);
  });
  it('still strips the real markup tags, then decodes', () => {
    expect(parseBriefText('<b>R&amp;D &lt;NRP&gt;</b>')).toEqual([{ type: 'header', text: 'R&D <NRP>' }]);
    expect(parseBriefText('<i>Stardate 2026.288 · 07:00 AEST</i>')).toEqual([
      { type: 'subtitle', text: 'Stardate 2026.288 · 07:00 AEST' },
    ]);
    expect(parseBriefText('Capacity <b>Green</b> &amp; <code>ok</code>')).toEqual([
      { type: 'text', text: 'Capacity Green & ok' },
    ]);
  });
  it('keeps blank lines and plain lines exactly as before', () => {
    expect(parseBriefText('Plain line\n\n<b>HEADER</b>')).toEqual([
      { type: 'text', text: 'Plain line' },
      { type: 'blank' },
      { type: 'header', text: 'HEADER' },
    ]);
  });
  it('treats a decoded "<script>" as data, never as markup to strip or run', () => {
    expect(parseBriefText('&lt;script&gt;alert(1)&lt;/script&gt;')).toEqual([
      { type: 'text', text: '<script>alert(1)</script>' },
    ]);
  });
});

describe('toSpokenText', () => {
  it('speaks the characters, not the entities', () => {
    expect(toSpokenText('<b>Update</b>\nregarding &lt;NRP&gt; &amp; more')).toBe('Update regarding <NRP> & more');
  });
  it('strips tags and emoji and collapses whitespace as before', () => {
    expect(toSpokenText('<b>☀️ MORNING BRIEF</b>\n\n  Capacity   <b>Green</b>')).toBe('MORNING BRIEF Capacity Green');
  });
  it('leaves plain and pre-escaping text unchanged', () => {
    expect(toSpokenText('Plain sentence about AT&T.')).toBe('Plain sentence about AT&T.');
  });
});
