// Checks that the HQ brand mark survives Windows High Contrast / forced
// colours. It loads the shipped SVG through <img> (as BrandMark does) on a
// page that carries HQ's own globals.css rule `* { forced-color-adjust: auto }`
// (read from the file, not retyped), emulates forced colours in Chromium, and
// fails if the tile and the mark are painted in a single colour.
// Usage (from lcars-portal/): node scripts/brand/check-forced-colours.mjs
// Needs Playwright's Chromium (set PLAYWRIGHT_CHROMIUM_EXECUTABLE if needed).
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const css = fs.readFileSync(path.join(root, 'src/app/globals.css'), 'utf8');
const rule = css.match(/\*,\s*\*::before,\s*\*::after\s*\{\s*forced-color-adjust:\s*auto;\s*\}/);
if (!rule) throw new Error('HQ forced-color-adjust rule not found in globals.css');

const files = ['hq-icon-light.svg', 'hq-icon-dark.svg'];
const exe = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
const browser = await chromium.launch({ executablePath: exe || undefined, args: ['--no-sandbox'] });
let failed = 0;

for (const [label, markup] of [
  ['inline SVG (the rejected approach)', (f) => fs.readFileSync(path.join(root, 'public/brand', f), 'utf8')],
  ['<img> (BrandMark)', (f) => `<img width="64" height="64" alt="" src="data:image/svg+xml;base64,${fs.readFileSync(path.join(root, 'public/brand', f)).toString('base64')}">`],
]) {
  for (const f of files) {
    const ctx = await browser.newContext({ forcedColors: 'active', viewport: { width: 200, height: 120 } });
    const page = await ctx.newPage();
    await page.setContent(`<style>${rule[0]} svg,img{width:64px;height:64px;display:block}</style><body style="margin:20px">${markup(f)}</body>`);
    const buf = await page.screenshot({ clip: { x: 20, y: 20, width: 64, height: 64 } });
    // Sample a pixel inside the tile (near its left edge) and a pixel on the
    // mark (the left stem of the H, 64-unit grid x=22, y=32). If forced colours
    // repaint both in one system colour, the mark has vanished.
    const px = await page.evaluate(async (b64) => {
      const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
      const c = document.createElement('canvas'); c.width = 64; c.height = 64; const x = c.getContext('2d'); x.drawImage(img, 0, 0);
      const at = (X, Y) => Array.from(x.getImageData(X, Y, 1, 1).data.slice(0, 3)).join(',');
      return { tile: at(6, 32), mark: at(22, 24) };
    }, buf.toString('base64'));
    const distinguishable = px.tile !== px.mark;
    console.log(`${distinguishable ? 'PASS' : 'FAIL'}  ${label}  ${f}  tile ${px.tile}  mark ${px.mark}`);
    if (label.startsWith('<img>') && !distinguishable) failed++;
    await ctx.close();
  }
}
await browser.close();
process.exit(failed ? 1 : 0);
