import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { inflateSync } from 'node:zlib';
import path from 'node:path';
import OpenGraphImage, { alt, size, contentType } from '../app/opengraph-image';
import { OG_LOCKUP_DATA_URI, OG_LOCKUP_HEIGHT, OG_LOCKUP_WIDTH } from '../app/ogLockup';

// Minimal PNG decoder (8-bit, non-interlaced, colour type 2 or 6) so the test can
// look at real pixels without a dependency.
function decodePng(buf: Buffer) {
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20), depth = buf[24], ct = buf[25], interlace = buf[28];
  if (depth !== 8 || interlace !== 0 || (ct !== 2 && ct !== 6)) throw new Error(`unsupported PNG ${depth}/${ct}/${interlace}`);
  const bpp = ct === 6 ? 4 : 3;
  const idat: Buffer[] = [];
  for (let o = 8; o < buf.length; ) {
    const len = buf.readUInt32BE(o), type = buf.toString('ascii', o + 4, o + 8);
    if (type === 'IDAT') idat.push(buf.subarray(o + 8, o + 8 + len));
    o += 12 + len;
  }
  const raw = inflateSync(Buffer.concat(idat));
  const stride = w * bpp, out = Buffer.alloc(h * stride);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)];
    for (let x = 0; x < stride; x++) {
      const v = raw[y * (stride + 1) + 1 + x];
      const a = x >= bpp ? out[y * stride + x - bpp] : 0;
      const b = y > 0 ? out[(y - 1) * stride + x] : 0;
      const c = x >= bpp && y > 0 ? out[(y - 1) * stride + x - bpp] : 0;
      const pa = Math.abs(b - c), pb = Math.abs(a - c), pc = Math.abs(a + b - 2 * c);
      const paeth = pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      out[y * stride + x] = (v + (f === 0 ? 0 : f === 1 ? a : f === 2 ? b : f === 3 ? (a + b) >> 1 : paeth)) & 255;
    }
  }
  return { w, h, px: (x: number, y: number) => [...out.subarray(y * stride + x * bpp, y * stride + x * bpp + 3)] };
}

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

  it('draws the lockup: mist background, navy tile and text pixels present, and the artwork is centred', async () => {
    const png = decodePng(Buffer.from(await OpenGraphImage().arrayBuffer()));
    const near = (c: number[], t: number[], tol = 12) => c.every((v, i) => Math.abs(v - t[i]) <= tol);
    const MIST = [245, 247, 250], NAVY = [16, 43, 70];
    for (const [x, y] of [[5, 5], [1194, 5], [5, 624], [1194, 624], [600, 40]]) expect(near(png.px(x, y), MIST), `bg ${x},${y}`).toBe(true);
    let minX = png.w, maxX = -1, minY = png.h, maxY = -1, navy = 0;
    for (let y = 0; y < png.h; y += 2) {
      for (let x = 0; x < png.w; x += 2) {
        if (!near(png.px(x, y), MIST, 40)) {
          minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
          if (near(png.px(x, y), NAVY, 12)) navy++;
        }
      }
    }
    expect(navy).toBeGreaterThan(2000); // the navy tile and "TJR" are drawn
    expect(Math.abs((minX + maxX) / 2 - png.w / 2)).toBeLessThan(30); // horizontally centred
    expect(Math.abs((minY + maxY) / 2 - png.h / 2)).toBeLessThan(30); // vertically centred
    expect(maxX - minX).toBeGreaterThan(800); // the lockup is large, not a speck
  });
});
