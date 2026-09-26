# Starship Endeavour — LCARS Web Portal

A **LCARS-style command dashboard** for **USS TJR — Starship Endeavour
(NCC-170230)**, built with **Next.js + React + TypeScript + Tailwind CSS**.

> **2026-09-26 correction:** this README described a pre-activation "Phase 1,
> placeholder-data-only" state, a port that hasn't been current since
> 2026-08-11, and dependencies (Dashy, a Slack bot) that have since been
> fully retired. The portal has been live with real Supabase-backed data on
> **`:3200`**, fronted by Caddy, since August/September 2026 — see
> `USS-TJR-Control/README.md` for the current whole-platform topology. This
> file is scoped to the portal itself.

For the current, real list of live pages/workbenches, read
**`src/lib/workbenches.ts`** — it's the app's own single source of truth
(both the hub tile grid and the persistent switcher render directly from it),
not this README. A page's absence from that file means legacy, deprecated,
experimental, or deliberately zero-nav — see that file's own header comment.

## Reusable components (`src/components/`)

- **LCARSHeader** — top command bar with the signature LCARS elbow + readouts.
- **LCARSNav** — left command rail, colour-coded by department, active-route aware.
- **LCARSPanel** — base content container with a department-accented title rail.
- **StatusBadge** — state pill; pass an explicit `tone` or let it infer one.
- **MissionCard** — mission readout (shape matches the mission registry rows).
- **DepartmentCard** — at-a-glance department summary with metrics.
- ~~AlertPanel~~ — no longer exists in `src/components/`; this line is stale, not re-verified further.

## Department colours (`src/lib/departments.ts` + `tailwind.config.ts`)

| Department | Colour | Hex |
|------------|--------|-----|
| Command | Command Gold | `#FFB81C` |
| Engineering | Engineering Orange | `#FF9800` |
| Operations | Operations Red | `#F44336` |
| Medical | Medical Blue | `#0099FF` |
| Science | Science Purple | `#CC88FF` |
| Status | Status Green | `#4CAF50` |

Hex values are aligned with the existing Command Centre theme
(`core/command-centre/theme-starfleet-advanced.css`) for visual consistency.

---

## Local development

Requires **Node.js ≥ 18.18**.

```bash
cd lcars-portal
npm install
npm run dev
# open http://localhost:3200  (redirects to /captains-chair)
```

Other scripts:

```bash
npm run build   # production build (also type-checks + lints)
npm run start   # serve the production build on port 3200
npm run lint    # eslint (next/core-web-vitals)
```

---

## Deployment

**Live today:** `lcars-portal.service` (systemd), Node server, `:3200`,
fronted by Caddy — deploy is `npm run build` + `systemctl restart
lcars-portal`. See `USS-TJR-Control/README.md`.

The Vercel-specific config below (`vercel.json`) is also present in this
directory — whether Vercel is a currently-live second deployment target or a
leftover from an earlier deploy approach was **not verified** in this pass;
confirm before treating both as authoritative.

`vercel.json`'s `ignoreCommand` skips the build entirely when a push doesn't
touch anything under this directory (TJRHQ is a large multi-service monorepo
where most commits — Python services, docs, other bots — never touch the
portal). This assumes the Vercel project's Root Directory is set to
`lcars-portal/` (per Option B above), which makes the ignore command run
with this directory as its working directory. It compares against
`VERCEL_GIT_PREVIOUS_SHA` (the last successfully-deployed commit on the
branch) rather than just `HEAD^`, so a multi-commit push is diffed in
full — falling back to `HEAD^` only for the very first push after this
config lands, when that variable isn't set yet.

`vercel.json` also disables automatic deployments for `dependabot/**`
branches outright (`git.deploymentEnabled`) — those are the single
biggest source of noise (a bump to some unrelated Python service's
`requirements.txt` still triggered a full portal deployment before this),
and GitHub Actions CI already validates them. A Dependabot bump that does
touch `lcars-portal/` (e.g. a JS dependency) still gets validated by CI
and picked up by the next production deploy once merged to `main`.

---

## Mobile Command MVP (MSN-IOS-001)

An iPhone-first, installable-PWA Command Centre MVP for five Captain-facing
surfaces — **Captain's Chair**, **Quick Capture** (`/capture`), **XO Chat**
(`/xo`), **Engineering Queue** (`/engineering-queue`) and **Push Alerts**
(`/alerts`) — all reusing the existing Supabase data, XO/Ollama context,
Engineering lifecycle and notification patterns (no parallel backend). A
mobile-only bottom command bar links the five surfaces; the desktop portal is
unchanged. Re-generate PWA icons with `node scripts/gen-icons.mjs`.

- [`docs/MOBILE-MVP.md`](docs/MOBILE-MVP.md) — strategy, reuse/API mapping, alert rules, future native phase.
- [`docs/MOBILE-MVP-VALIDATION.md`](docs/MOBILE-MVP-VALIDATION.md) — WP8 validation & test evidence.

## Documentation

- [`docs/ACCEPTANCE-CRITERIA.md`](docs/ACCEPTANCE-CRITERIA.md) — Phase 1 acceptance criteria.
- [`docs/SMOKE-TEST-CHECKLIST.md`](docs/SMOKE-TEST-CHECKLIST.md) — manual smoke test checklist.
