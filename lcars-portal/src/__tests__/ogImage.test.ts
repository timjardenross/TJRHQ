import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import OpenGraphImage, { alt, size, contentType } from '../app/opengraph-image';
import { OG_LOCKUP_DATA_URI, OG_LOCKUP_HEIGHT, OG_LOCKUP_WIDTH } from '../app/ogLockup';

describe('Open Graph image (brand Stage 3)', () => {
  it('embeds exactly the shipped primary lockup SVG', () => {
    const file = readFileSync(path.join(process.cwd(), 'public', 'brand', 'hq-wordmark-primary-light.svg'));
    const b64 = OG_LOCKUP_DATA_URI.replace('data:image/svg+xml;base64,', '');
    expect(Buffer.from(b64, 'base64').equals(file)).toBe(true);
    const m = file.toString('utf8').match(/width="(\d+)" height="(\d+)"/)!;
    expect([OG_LOCKUP_WIDTH, OG_LOCKUP_HEIGHT]).toEqual([Number(m[1]), Number(m[2])]);
  });

  it('declares a 1200x630 PNG named for TJR HQ, with no retired wording', () => {
    expect(size).toEqual({ width: 1200, height: 630 });
    expect(contentType).toBe('image/png');
    expect(alt).toBe('TJR HQ, Intelligence & Operations Centre');
    expect(alt).not.toMatch(/endeavour/i);
  });

  it('renders a real 1200x630 PNG', async () => {
    const res = OpenGraphImage();
    expect(res.headers.get('content-type')).toBe('image/png');
    const buf = Buffer.from(await res.arrayBuffer());
    expect(buf.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
    expect([buf.readUInt32BE(16), buf.readUInt32BE(20)]).toEqual([1200, 630]);
  });
});
