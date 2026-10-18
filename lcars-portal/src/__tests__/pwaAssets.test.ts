import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const pub = (f: string) => path.join(root, 'public', f);

type Icon = { src: string; sizes: string; type: string; purpose: string };
const manifest = JSON.parse(readFileSync(pub('manifest.webmanifest'), 'utf8')) as {
  description: string;
  theme_color: string;
  background_color: string;
  icons: Icon[];
};

function pngInfo(file: string) {
  const b = readFileSync(file);
  expect(b.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20), colourType: b[25] };
}

describe('PWA manifest and icons (brand Stage 1)', () => {
  it('every manifest icon exists with the declared size and purpose', () => {
    expect(manifest.icons.map((i) => i.purpose).sort()).toEqual(['any', 'any', 'maskable']);
    for (const icon of manifest.icons) {
      const file = pub(icon.src.replace(/^\//, ''));
      expect(existsSync(file), icon.src).toBe(true);
      const [w, h] = icon.sizes.split('x').map(Number);
      const info = pngInfo(file);
      expect({ src: icon.src, w: info.w, h: info.h }).toEqual({ src: icon.src, w, h });
    }
  });

  it('the apple touch icon is 180 px', () => {
    const info = pngInfo(pub('apple-touch-icon.png'));
    expect([info.w, info.h]).toEqual([180, 180]);
  });

  it('PNG icons are opaque (RGB, no alpha channel): the platform applies its own mask', () => {
    for (const f of ['icon-192.png', 'icon-512.png', 'icon-maskable-512.png', 'apple-touch-icon.png']) {
      expect(pngInfo(pub(f)).colourType, f).toBe(2);
    }
  });

  it('keeps theme and background colours unchanged until the light re-theme (owner decision)', () => {
    expect(manifest.theme_color).toBe('#05070e');
    expect(manifest.background_color).toBe('#05070e');
  });

  it('the description no longer uses the retired "Captain\'s Chair" wording', () => {
    expect(manifest.description).not.toMatch(/captain/i);
  });

  it('favicon.ico holds 16, 32 and 48 px PNG images', () => {
    const b = readFileSync(path.join(root, 'src', 'app', 'favicon.ico'));
    expect([b.readUInt16LE(0), b.readUInt16LE(2)]).toEqual([0, 1]);
    const count = b.readUInt16LE(4);
    const sizes: number[] = [];
    for (let i = 0; i < count; i++) {
      const e = 6 + i * 16;
      sizes.push(b[e]);
      const len = b.readUInt32LE(e + 8), off = b.readUInt32LE(e + 12);
      expect(b.subarray(off, off + 8).toString('hex')).toBe('89504e470d0a1a0a');
      expect(off + len).toBeLessThanOrEqual(b.length);
    }
    expect(sizes).toEqual([16, 32, 48]);
  });

  it('src/app/icon.svg is the adaptive HQ favicon, no longer the Mind & Body one', () => {
    const icon = readFileSync(path.join(root, 'src', 'app', 'icon.svg'), 'utf8');
    expect(icon).toBe(readFileSync(pub('brand/hq-favicon-adaptive.svg'), 'utf8'));
  });
});
