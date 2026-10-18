// Pixel checks on the generated PWA icons (run after build-icons.mjs).
//  - every PNG is fully opaque and its corner pixel is brand navy #102B46
//  - the mark (non-navy pixels) exists and is white
//  - maskable icon: every mark pixel lies inside the 40% safe-zone circle
// Usage (from lcars-portal/): node scripts/brand/check-icons.mjs
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const PUBLIC = path.join(process.cwd(), 'public');
const FILES = ['icon-192.png', 'icon-512.png', 'icon-maskable-512.png', 'apple-touch-icon.png'];
const exe = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
const browser = await chromium.launch({ executablePath: exe || undefined, args: ['--no-sandbox'] });
const page = await browser.newPage();
let failed = 0;
for (const f of FILES) {
  const b64 = fs.readFileSync(path.join(PUBLIC, f)).toString('base64');
  const r = await page.evaluate(async (b64) => {
    const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
    const n = img.naturalWidth; const c = document.createElement('canvas'); c.width = n; c.height = n;
    const x = c.getContext('2d'); x.drawImage(img, 0, 0); const d = x.getImageData(0, 0, n, n).data;
    let transparent = 0, mark = 0, maxR = 0, whiteMark = 0;
    const cx = n / 2, cy = n / 2;
    for (let i = 0; i < d.length; i += 4) {
      if (d[i + 3] !== 255) transparent++;
      const isNavy = Math.abs(d[i] - 16) < 6 && Math.abs(d[i + 1] - 43) < 6 && Math.abs(d[i + 2] - 70) < 6;
      if (!isNavy) {
        mark++;
        const p = i / 4; const dx = (p % n) + 0.5 - cx, dy = Math.floor(p / n) + 0.5 - cy;
        maxR = Math.max(maxR, Math.hypot(dx, dy) / n);
        if (d[i] > 250 && d[i + 1] > 250 && d[i + 2] > 250) whiteMark++;
      }
    }
    return { n, transparent, mark, whiteMark, maxR, corner: [d[0], d[1], d[2]] };
  }, b64);
  const cornerOk = r.corner[0] === 16 && r.corner[1] === 43 && r.corner[2] === 70;
  const safeOk = f !== 'icon-maskable-512.png' || r.maxR <= 0.4;
  const ok = r.transparent === 0 && cornerOk && r.mark > 0 && r.whiteMark > 0 && safeOk;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${f}  ${r.n}px  transparent=${r.transparent} corner=${r.corner} markPx=${r.mark} farthest=${(r.maxR * 100).toFixed(1)}% of size`);
  if (!ok) failed++;
}
await browser.close();
process.exit(failed ? 1 : 0);
