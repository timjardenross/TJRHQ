# MSN-IOS-001 — Mobile MVP Validation (WP8)

Validation evidence for the five MVP surfaces. Run from `lcars-portal/`.

## 1. Build / typecheck / lint — PASS

`npm run build` compiles, type-checks and lints the whole portal including all
new surfaces. Evidence (abridged):

```
✓ Compiled successfully
  Linting and checking validity of types ...
✓ Generating static pages (31/31)

Route (app)
├ ○ /alerts                       4.33 kB
├ ƒ /api/xo                       0 B
├ ○ /captains-chair              7.18 kB
├ ○ /capture                     3.5 kB
├ ○ /engineering-queue           5.02 kB
├ ○ /xo                          3.65 kB
```

All five MVP routes (`/captains-chair`, `/capture`, `/xo`,
`/engineering-queue`, `/alerts`) plus the `/api/xo` endpoint are present. No
type errors, no lint errors.

## 2. PWA / iOS installability — PASS (static checks)

| Check | Result |
|-------|--------|
| `public/manifest.webmanifest` valid JSON, `display: standalone`, `start_url`, icons | ✅ |
| Maskable + any-purpose 192/512 icons present, valid PNG | ✅ (rendered & verified) |
| `apple-touch-icon.png` (180×180) present | ✅ |
| `appleWebApp` + `manifest` + `viewport(themeColor, viewport-fit=cover)` in `layout.tsx` | ✅ |
| Service worker `public/sw.js` registered via `ServiceWorkerRegister` | ✅ |
| Middleware allows `sw.js` + `manifest.webmanifest` unauthenticated | ✅ |
| SW never caches navigations/auth responses (no stale-session risk) | ✅ |

iOS install path: Safari → Share → **Add to Home Screen** → launches standalone
with the LCARS icon. Web Push banners require iOS 16.4+ installed PWA + opt-in on
`/alerts`.

## 3. Existing-data reuse — PASS (no new backend)

Confirmed by inspection that the new code adds **no** tables/views/RPCs/edge
functions/services. Every fetcher reads tables already populated by the
portal/Slack/Telegram systems (see `docs/MOBILE-MVP.md` → "Reused backend / API
mapping"). Quick Capture writes only to `captured_items`, whose schema grants the
`authenticated` role insert/select/update.

## 4. No broken web access — PASS

- The desktop Captain's Chair grid is unchanged; the mobile operating picture is
  additive and `lg:hidden`.
- `MobileCommandBar` is `lg:hidden` — desktop navigation untouched.
- All pre-existing routes still build and render (31/31 static pages generated).
- Auth middleware unchanged except for two static-asset allowances.

## 5. No duplicate command workflows — PASS

- Capture → existing `captured_items` registry (not a new inbox).
- XO → existing Ollama upstream + `buildShipContext` (not a new AI service).
- Engineering Queue → existing `build_request_inbox` + `mission_delivery`
  lifecycle (not a new tracker).
- Alerts → derived from existing data (no new alert store).

## 6. Alerts gated & meaningful — PASS

`lib/alerts.ts` emits only the five permitted classes, each behind a specific
threshold; healthy conditions emit nothing; every alert carries a `why`.
Notifications fire only for newly-appeared critical/high alerts and never repeat
(signature persisted). See alert-rules table in `docs/MOBILE-MVP.md`.

## 7. End-to-end manual smoke checklist

Run `npm run dev` (port 3100) with `.env.local` pointing at the live Supabase
project, sign in, then on a phone (or DevTools device emulation):

- [ ] **Captain's Chair** — operating picture renders; "What needs my decision?"
      banner reflects current alerts; capacity band matches today's posture.
- [ ] **Quick Capture** — type a note, tap Capture → appears in "Recently
      captured"; switch type to Mission → captured with `mission` classification;
      Health type shows the "full check-in" link.
- [ ] **XO Chat** — send "What needs my decision today?" → brief answer ending in
      `→ Next action:`; with model disabled, the action row still captures/routes.
- [ ] **Engineering Queue** — items grouped into the 5 lifecycle buckets; blockers
      listed; next-action hero set; Approve/Reject on an awaiting-review build item
      reports a real outcome.
- [ ] **Push Alerts** — only gated alerts shown; "All clear" when none; Enable
      notifications → permission prompt → banner on next new critical/high alert;
      tapping a banner deep-links to the right surface.
- [ ] **PWA** — Add to Home Screen; launches standalone; icon correct; bottom
      command bar thumb-reachable with safe-area inset.

> Note: live end-to-end behaviour depends on the Supabase project's data and RLS.
> Surfaces degrade gracefully (empty / "no data" states) when a query returns
> nothing or is not permitted — verified by the offline build and by the
> null-guards in every fetcher.
