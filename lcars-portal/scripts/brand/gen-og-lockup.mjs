// Regenerates src/app/ogLockup.ts from public/brand/hq-wordmark-primary-light.svg.
// Usage (from lcars-portal/): node scripts/brand/gen-og-lockup.mjs
import fs from 'node:fs';
const svg = fs.readFileSync('public/brand/hq-wordmark-primary-light.svg');
const m = svg.toString('utf8').match(/width="(\d+)" height="(\d+)"/);
const out = `// GENERATED from public/brand/hq-wordmark-primary-light.svg by scripts/brand/gen-og-lockup.mjs.
// The edge OG renderer cannot read files, so the outlined lockup is embedded as a data URI.
// src/__tests__/ogImage.test.ts checks this stays identical to the public file.
export const OG_LOCKUP_WIDTH = ${m[1]};
export const OG_LOCKUP_HEIGHT = ${m[2]};
export const OG_LOCKUP_DATA_URI = 'data:image/svg+xml;base64,${svg.toString('base64')}';
`;
fs.writeFileSync('src/app/ogLockup.ts', out);
console.log('wrote src/app/ogLockup.ts', m[1], m[2]);
