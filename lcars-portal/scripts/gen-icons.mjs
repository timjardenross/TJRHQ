// Generates LCARS-style PWA icons (PNG) with zero dependencies.
// Pure rectangles + rounded corners — no font rasterisation required.
// Run: node scripts/gen-icons.mjs
import { deflateSync } from 'node:zlib';
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = join(__dirname, '..', 'public');
mkdirSync(OUT, { recursive: true });

// LCARS palette (matches tailwind.config.ts)
const SPACE = [5, 7, 14, 255];
const PANEL = [18, 22, 46, 255];
const GOLD = [255, 184, 28, 255];
const ORANGE = [255, 152, 0, 255];
const BLUE = [0, 153, 255, 255];
const LILAC = [153, 153, 255, 255];

function crc32(buf) {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return ~c >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const t = Buffer.from(type, 'ascii');
  const body = Buffer.concat([t, data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body), 0);
  return Buffer.concat([len, body, crc]);
}
function png(width, height, rgba) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // colour type RGBA
  // rest 0 (compression, filter, interlace)
  const stride = width * 4;
  const raw = Buffer.alloc((stride + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (stride + 1)] = 0; // filter none
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, y * stride + stride);
  }
  const idat = deflateSync(raw, { level: 9 });
  return Buffer.concat([
    sig,
    chunk('IHDR', ihdr),
    chunk('IDAT', idat),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

function makeIcon(size, { maskable = false } = {}) {
  const buf = Buffer.alloc(size * size * 4);
  const set = (x, y, c) => {
    if (x < 0 || y < 0 || x >= size || y >= size) return;
    const i = (y * size + x) * 4;
    buf[i] = c[0]; buf[i + 1] = c[1]; buf[i + 2] = c[2]; buf[i + 3] = c[3];
  };
  const fillRect = (x0, y0, w, h, c) => {
    for (let y = y0; y < y0 + h; y++) for (let x = x0; x < x0 + w; x++) set(x, y, c);
  };
  // Rounded-rect fill with corner radius r
  const roundRect = (x0, y0, w, h, r, c) => {
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let inside = true;
        // corners
        const corners = [
          [r, r], [w - r - 1, r], [r, h - r - 1], [w - r - 1, h - r - 1],
        ];
        if (x < r && y < r) inside = (x - r) ** 2 + (y - r) ** 2 <= r * r;
        else if (x > w - r - 1 && y < r) inside = (x - (w - r - 1)) ** 2 + (y - r) ** 2 <= r * r;
        else if (x < r && y > h - r - 1) inside = (x - r) ** 2 + (y - (h - r - 1)) ** 2 <= r * r;
        else if (x > w - r - 1 && y > h - r - 1) inside = (x - (w - r - 1)) ** 2 + (y - (h - r - 1)) ** 2 <= r * r;
        if (inside) set(x0 + x, y0 + y, c);
      }
    }
  };

  // Background
  const bgR = maskable ? 0 : Math.round(size * 0.18);
  fillRect(0, 0, size, size, SPACE);
  if (!maskable) {
    // give non-maskable a rounded space tile
    roundRect(0, 0, size, size, bgR, SPACE);
  }

  // Safe area inset for maskable (keep art within central 80%)
  const inset = maskable ? Math.round(size * 0.14) : Math.round(size * 0.13);
  const ax = inset, ay = inset;
  const aw = size - inset * 2, ah = size - inset * 2;
  const unit = Math.round(aw * 0.06);

  // LCARS left command bar (gold) with rounded outer corners
  const barW = Math.round(aw * 0.26);
  roundRect(ax, ay, barW, ah, Math.round(barW * 0.45), GOLD);
  // square off the inner (right) edge by overpainting a rectangle
  fillRect(ax + Math.round(barW * 0.5), ay, Math.round(barW * 0.5), ah, GOLD);

  // Horizontal rails to the right of the bar
  const railX = ax + barW + unit;
  const railW = aw - barW - unit;
  const railH = Math.round(ah * 0.16);
  const gap = Math.round(ah * 0.07);
  roundRect(railX, ay, railW, railH, Math.round(railH * 0.5), ORANGE);
  roundRect(railX, ay + railH + gap, Math.round(railW * 0.62), railH, Math.round(railH * 0.5), BLUE);
  roundRect(railX, ay + (railH + gap) * 2, Math.round(railW * 0.8), railH, Math.round(railH * 0.5), LILAC);

  // Lower readout panel
  const panelY = ay + (railH + gap) * 3;
  const panelH = ay + ah - panelY;
  if (panelH > unit) roundRect(railX, panelY, railW, panelH, Math.round(unit), PANEL);

  return png(size, size, buf);
}

const targets = [
  ['icon-192.png', 192, {}],
  ['icon-512.png', 512, {}],
  ['icon-maskable-512.png', 512, { maskable: true }],
  ['apple-touch-icon.png', 180, {}],
];
for (const [name, size, opts] of targets) {
  writeFileSync(join(OUT, name), makeIcon(size, opts));
  console.log('wrote', name, size);
}
