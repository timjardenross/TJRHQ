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

- Tile follows the surface: `surface="light"` navy tile, `surface="dark"` inverted tile. The dark sidebar uses the inverted tile; the header uses the navy tile in light Read mode.
- Render as `<img>` (the components do). HQ's global `forced-color-adjust: auto` hides an inline SVG mark in forced-colours mode. Check: `node scripts/brand/check-forced-colours.mjs`.
- The mark is decorative by default (`alt=""`); name the parent link or button. Give `label` only when it stands alone.
- Minimum sizes: mark 16 px (use the favicon cuts below 32 px on light); primary lockup 310 px wide (descriptor stays 12 px or more); horizontal 160 px; compact 72 px. Show the descriptor in the primary lockup only, not in the sidebar or login heading.
- Clear space: the cap height of "TJR" on every side.
- Do not recolour, outline, add effects, stretch, rotate, or place the navy tile directly on navy.

## Decisions recorded for this stage

- **Stage 0 changes nothing visible.** The components and files are not used by any page yet.
- **First paint, manifest and theme colours are unchanged** (`manifest.webmanifest`, both `themeColor` values). They change once, from the re-themed tokens, when the light-default re-theme ships. Icons only change in Stage 1 (with a service-worker cache bump and `cache: 'reload'`).
- `--brand-*` tokens are additive; no `--wb-*` value changes or maps to them yet.
