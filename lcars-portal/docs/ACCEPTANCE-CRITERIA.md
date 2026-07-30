# Acceptance Criteria — LCARS Web Portal Phase 1

**Mission:** Build Starship LCARS Web Portal Phase 1
**Status target:** Static and navigable, placeholder data only.

A criterion is met (✅) when it is verifiably true in the running app or repo.

## Stack & structure

- [x] **AC-1** New frontend app exists in the repo (`lcars-portal/`), self-contained.
- [x] **AC-2** Built with Next.js, React, TypeScript and Tailwind CSS.
- [x] **AC-3** `npm install && npm run build` completes with no type or lint errors.

## Pages (all present and navigable)

- [x] **AC-4** Captain's Chair (`/captains-chair`, also served at `/`).
- [x] **AC-5** Missions (`/missions`).
- [x] **AC-6** Engineering (`/engineering`).
- [x] **AC-7** Number One (`/number-one`).
- [x] **AC-8** XO Brief (`/xo-brief`).
- [x] **AC-9** Medical / Wellness (`/medical`).
- [x] **AC-10** Operations (`/operations`).
- [x] **AC-11** Knowledge Base (`/knowledge-base`).
- [x] **AC-12** Every page is reachable from the LCARS nav, which highlights the active route.

## Reusable components

- [x] **AC-13** `LCARSHeader`, `LCARSNav`, `LCARSPanel`, `StatusBadge`, `MissionCard`,
  `DepartmentCard`, `AlertPanel` all exist in `src/components/` and are reused
  across multiple pages.

## Department colours

- [x] **AC-14** Command Gold, Engineering Orange, Operations Red, Medical Blue,
  Science Purple and Status Green are defined once (`tailwind.config.ts` +
  `src/lib/departments.ts`) and applied consistently via department accents.

## Data

- [x] **AC-15** All domain/placeholder data lives in a single file
  (`src/lib/mockData.ts`); no other file hardcodes domain data.
- [x] **AC-16** Mock data shapes mirror existing backend responses, and each
  export documents its target live endpoint (Phase 2 swap-in).
- [x] **AC-17** No live API calls are made in Phase 1 (fully static/navigable).

## Non-regression (must not break existing systems)

- [x] **AC-18** No existing files were modified outside `lcars-portal/`.
- [x] **AC-19** Dashy, Slack bot, Commander backend, Context Assembly and
  Supabase code/config are untouched; the portal runs on its own port (3100),
  avoiding collisions (Dashy 8000, backend 5050, Slack bot 3001).

## Documentation

- [x] **AC-20** README covers local dev and deployment.
- [x] **AC-21** Acceptance criteria (this file) and a smoke test checklist exist.
- [x] **AC-22** Work is committed on the designated feature branch.
