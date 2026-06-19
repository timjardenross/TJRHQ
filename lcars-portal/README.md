# Starship Endeavour — LCARS Web Portal (Phase 1)

A reusable **LCARS-style command dashboard** for **USS TJR — Starship Endeavour
(NCC-170230)**, built with **Next.js + React + TypeScript + Tailwind CSS**.

> **Phase 1 scope:** static and navigable, **placeholder data only**. No live
> backend calls are wired up yet. All domain data lives in a single file
> (`src/lib/mockData.ts`) so Phase 2 can swap mocks for live API calls without
> touching any page or component.

This app is **additive**. It does **not** modify or depend on the existing
Dashy Control Deck, Number One Slack bot, Commander (Command Centre) backend,
Context Assembly service, or Supabase integrations — it lives in its own
`lcars-portal/` directory and runs on its own port (**3100**).

---

## Pages

| Route | Page | Department accent |
|-------|------|-------------------|
| `/` → `/captains-chair` | Captain's Chair | Command Gold |
| `/missions` | Missions | Command Gold |
| `/engineering` | Engineering | Engineering Orange |
| `/number-one` | Number One | Operations Red |
| `/xo-brief` | XO Brief | Science Purple |
| `/medical` | Medical / Wellness | Medical Blue |
| `/operations` | Operations | Operations Red |
| `/knowledge-base` | Knowledge Base | Science Purple |

## Reusable components (`src/components/`)

- **LCARSHeader** — top command bar with the signature LCARS elbow + readouts.
- **LCARSNav** — left command rail, colour-coded by department, active-route aware.
- **LCARSPanel** — base content container with a department-accented title rail.
- **StatusBadge** — state pill; pass an explicit `tone` or let it infer one.
- **MissionCard** — mission readout (shape matches the mission registry rows).
- **DepartmentCard** — at-a-glance department summary with metrics.
- **AlertPanel** — stacked, severity-coded alert list.

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
# open http://localhost:3100  (redirects to /captains-chair)
```

Other scripts:

```bash
npm run build   # production build (also type-checks + lints)
npm run start   # serve the production build on port 3100
npm run lint    # eslint (next/core-web-vitals)
```

---

## Deployment

The portal is a standard Next.js app and deploys anywhere Next.js is supported.

**Option A — Node server (recommended for the local fleet):**

```bash
cd lcars-portal
npm ci
npm run build
npm run start        # listens on :3100
```

Put it behind the existing reverse proxy / Dashy as another card, or run it
alongside the Command Centre backend.

**Option B — Vercel / static host:** push the repo and point the platform at
the `lcars-portal/` directory; the default build command (`next build`) and
output are used as-is.

**Port note:** 3100 is chosen to avoid collisions with existing services
(Dashy `8000`, Command Centre backend `5050`, Slack bot `3001`).

---

## Phase 2 — wiring live data

All data is centralised in **`src/lib/mockData.ts`**. Each export is annotated
with the existing Command Centre endpoint it maps onto, e.g.:

| Mock export | Live endpoint (existing backend) |
|-------------|----------------------------------|
| `missions`, `missionSummary` | `GET /api/v1/missions/active`, `/summary` |
| `captainBrief` | `GET /api/v1/context/captain-brief` |
| `operatingPicture` | `GET /api/v1/context/operating-picture` |
| `alerts` | `GET /api/v1/health/alerts` |
| `crew` | `GET /api/v1/agents/status` |
| `wellness` | `GET /api/v1/personal-health` / `context/health` |
| `services` | `GET /api/v1/health/services` |
| `intelligenceBrief` | `GET /api/v1/intelligence/latest` |
| `knowledgeArticles` | `knowledge/` + Supabase knowledge prototype |

To go live: set `NEXT_PUBLIC_API_BASE_URL` (see `.env.example`), then replace
the static exports in `mockData.ts` with `fetch` calls returning the same typed
shapes (`src/lib/types.ts`). **No page or component code needs to change.**

---

## Documentation

- [`docs/ACCEPTANCE-CRITERIA.md`](docs/ACCEPTANCE-CRITERIA.md) — Phase 1 acceptance criteria.
- [`docs/SMOKE-TEST-CHECKLIST.md`](docs/SMOKE-TEST-CHECKLIST.md) — manual smoke test checklist.
