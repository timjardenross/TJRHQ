# TJR HQ brand assets

Source of truth for the TJR HQ identity ("Connected H"). Specification, rationale and review history:
`TJR-Ecosystem` repo, `architecture/design-system/brand/TJR-BRAND-FAMILY-AND-HQ-IDENTITY.md` (v1.1+).
Only HQ assets live here; the other four products' previews stay in that repository.

All SVGs are outlined paths (no live text), generated once by `tools/make_assets.py` in the ecosystem repo.
Do not hand-edit them; regenerate and replace.

## Files

| Group | Files |
|---|---|
| Icon | `hq-icon-light` (navy tile), `hq-icon-dark` (inverted mist tile), `hq-icon-mono-navy`, `hq-icon-mono-white` |
| Lockups | `hq-wordmark-primary-{light,dark}` (with descriptor), `-horizontal-`, `-compact-` (text only), `hq-wordmark-mono-{navy,white}` |
| Small sizes | `hq-favicon-16` (stroke 6), `hq-favicon-32` (stroke 4.6), `hq-favicon-adaptive` |
| App icon | `hq-app-icon-fullbleed` (no own corner radius: the OS masks it) |

## Use

Use the components, not raw paths: `import { BrandMark, BrandWordmark } from '@/components/brand'`.

- Tile follows the surface: `surface="light"` navy tile, `surface="dark"` inverted tile. The dark navy sidebar uses the inverted tile; the header and login sit on the default light surface and use the navy tile (the header uses the inverted tile only under `WorkbenchShell mode="dark"`).
- Render as `<img>` (the components do). HQ's global `forced-color-adjust: auto` hides an inline SVG mark in forced-colours mode. Check: `node scripts/brand/check-forced-colours.mjs`.
- The mark is decorative by default (`alt=""`); name the parent link or button. Give `label` only when it stands alone.
- Minimum sizes: mark 16 px (use the favicon cuts below 32 px on light); primary lockup 310 px wide (descriptor stays 12 px or more); horizontal 160 px; compact 72 px. Show the descriptor in the primary lockup only, not in the sidebar or login heading.
- Clear space: the cap height of "TJR" on every side.
- Do not recolour, outline, add effects, stretch, rotate, or place the navy tile directly on navy.

## Decisions recorded for this stage

- **Stage 0 changes nothing visible.** The components and files are not used by any page yet.
- **First paint, manifest and theme colours** were left unchanged in Stages 0 to 3 and now follow the light default (design uplift Stage A: `theme_color`, `background_color` and `themeColor` are `#F5F7FA`, with a service-worker cache bump to v3).
- `--brand-*` tokens are additive; no `--wb-*` value changes or maps to them yet.

## Gates carried to later stages (independent review of Stage 0, 2026-10-18)

- **Dark surface below 24 px:** no heavier-stroke dark cut exists. Add one before any dark-surface use under 24 px (Stage 2 uses 36 px).
- **Rendered checks:** the unit tests check constants, files and viewBox ratios only. Descriptor size, raster legibility and optical distinction at 16/32/64 px are rendered-output gates for the implementation stage, not proven here.
- **Forced colours:** `scripts/brand/check-forced-colours.mjs` is evidence for Chromium on this harness only. Windows High Contrast, other browsers, screen readers and devices are validated at the component release gate.
- **Release record:** before closing Stage 0, record the owner decision and re-check that no page imports these components and no `--wb-*` value changed.
- `mono` wordmark is horizontal-only; the component type rejects other layouts.

## Stage 1: icons, favicon, service worker

- `src/app/icon.svg` is the adaptive HQ favicon; `src/app/favicon.ico` holds 16/32/48 px images. `public/icon-192.png`, `icon-512.png`, `icon-maskable-512.png`, `apple-touch-icon.png` are rendered from `hq-app-icon-fullbleed.svg` (opaque navy, no own corner radius). Regenerate with `node scripts/brand/build-icons.mjs`; verify with `node scripts/brand/check-icons.mjs` (opaque, navy corner, white mark, maskable mark inside the 40% safe zone).
- `public/sw.js` cache is `lcars-static-v2` and precaches with `cache: 'reload'`. Any change to a precached file needs a new cache name, or installed apps keep the old copy (cache-first never revalidates).
- Manifest `theme_color` and `background_color` follow the light default (see above). Installed apps keep their old splash and title-bar colours until the manifest refreshes or the app is reinstalled.
- **Upgrade check (real files, real bytes):** `node scripts/brand/check-sw-migration.mjs <git-ref-of-old-version>`. It covers install, upgrade, a failed precache (the previous worker and cache must stay) and the documented rollback.
- **Failed precache:** the worker installs only if every precached file is fetched; otherwise the install is rejected, the previous worker and its cache stay, and the partial cache is removed.
- **Rollback:** revert the files AND bump the cache name again (v3), keeping `cache: 'reload'`. A plain revert to `v1` can re-serve the new icons from the HTTP cache where assets carry a long `max-age`.
- **iOS:** an existing home-screen icon will not update until the app is removed and re-added to the Home Screen.

## Stage 3: share image, reset page, wording

- `src/app/opengraph-image.tsx` renders the primary lockup on mist (1200x630). The edge renderer cannot read files, so `src/app/ogLockup.ts` embeds the SVG as a data URI; regenerate with `node scripts/brand/gen-og-lockup.mjs` after any lockup change (a test fails if they drift).
- `auth/reset-password` has the same heading as login: dark-surface mark, plain "TJR HQ".
- "Endeavour 27" is gone from visible strings and page metadata (`(auth)/layout.tsx`, `(app)/layout.tsx`, the OG image). Code comments that cite the old mission are history and stay.
