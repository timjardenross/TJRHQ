// Rasterises the TJR HQ brand SVGs into the PWA icons and favicon.ico.
// Usage (from lcars-portal/): node scripts/brand/build-icons.mjs
// Uses Playwright (already a devDependency); set PLAYWRIGHT_CHROMIUM_EXECUTABLE
// to point at a Chromium binary if Playwright's own is not installed.
// Replaces scripts/gen-icons.mjs (LCARS icons).
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const BRAND = path.join(root, 'public', 'brand');
const PUBLIC = path.join(root, 'public');

// Full-bleed navy tile with the white mark and no own corner radius: the OS
// applies its own mask (maskable, iOS) and "any" icons stay opaque squares.
const FULLBLEED = path.join(BRAND, 'hq-app-icon-fullbleed.svg');
const PNGS = [
  ['icon-192.png', 192],
  ['icon-512.png', 512],
  ['icon-maskable-512.png', 512],
  ['apple-touch-icon.png', 180],
];
// ICO: the heavier-stroke favicon cuts at 16 and 32, the standard icon at 48.
const ICO = [
  [16, 'hq-favicon-16.svg'],
  [32, 'hq-favicon-32.svg'],
  [48, 'hq-icon-light.svg'],
];

async function render(page, svgPath, size, transparent) {
  const svg = fs.readFileSync(svgPath);
  const uri = `data:image/svg+xml;base64,${svg.toString('base64')}`;
  await page.setViewportSize({ width: size, height: size });
  await page.setContent(
    `<style>html,body{margin:0;background:transparent}img{display:block;width:${size}px;height:${size}px}</style><img src="${uri}">`,
  );
  await page.evaluate(() => document.querySelector('img').decode());
  return page.screenshot({ type: 'png', omitBackground: transparent, clip: { x: 0, y: 0, width: size, height: size } });
}

function buildIco(entries) {
  // ICONDIR + ICONDIRENTRY[] + PNG payloads (PNG-in-ICO, supported since Vista).
  const head = Buffer.alloc(6);
  head.writeUInt16LE(0, 0); head.writeUInt16LE(1, 2); head.writeUInt16LE(entries.length, 4);
  let offset = 6 + 16 * entries.length;
  const dir = [];
  for (const { size, png } of entries) {
    const e = Buffer.alloc(16);
    e.writeUInt8(size >= 256 ? 0 : size, 0); e.writeUInt8(size >= 256 ? 0 : size, 1);
    e.writeUInt8(0, 2); e.writeUInt8(0, 3);
    e.writeUInt16LE(1, 4); e.writeUInt16LE(32, 6);
    e.writeUInt32LE(png.length, 8); e.writeUInt32LE(offset, 12);
    offset += png.length;
    dir.push(e);
  }
  return Buffer.concat([head, ...dir, ...entries.map((e) => e.png)]);
}

const exe = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
const browser = await chromium.launch({ executablePath: exe || undefined, args: ['--no-sandbox'] });
const page = await browser.newPage({ deviceScaleFactor: 1 });

for (const [name, size] of PNGS) {
  fs.writeFileSync(path.join(PUBLIC, name), await render(page, FULLBLEED, size, false));
  console.log('wrote', name, size);
}
const ico = [];
for (const [size, file] of ICO) ico.push({ size, png: await render(page, path.join(BRAND, file), size, true) });
fs.writeFileSync(path.join(root, 'src', 'app', 'favicon.ico'), buildIco(ico));
console.log('wrote src/app/favicon.ico', ICO.map(([s]) => s).join('/'));
await browser.close();
