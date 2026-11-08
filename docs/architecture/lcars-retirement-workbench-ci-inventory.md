# LCARS Retirement and Workbench CI Delivery Inventory

**Status:** Delivery discovery — no source deletion authorised by this document  
**Repository:** timjardenross/TJRHQ  
**Baseline:** main at `2f31199a4da13bd5790881e79861a265a9f84acd`

## Confirmed

- The legacy workflow `.github/workflows/lcars-portal-ci.yml` has been removed.
- Its active governance checks were moved to `.github/workflows/workbench-governance-ci.yml`.
- The workbench registry gate is preserved.
- No VM, production or deployment changes are part of this inventory.

## Remaining LCARS surface

The `lcars-portal/` tree still exists and must be treated as potentially active until references are checked. The repository's coordination route documentation identifies LCARS as a consumer of Number One data, while other comments describe the route as obsolete. These statements are inconsistent and require source-level confirmation before deleting code.

## Required inventory before source removal

Search the repository for:

- imports or fetches of `lcars-portal` routes;
- deployment, Caddy, Vercel and systemd references;
- package/build scripts and lockfile ownership;
- links from workbench pages, shared libraries or API clients;
- documentation and operator runbooks;
- external integrations and scheduled jobs.

Classify each reference as active, legacy, documentation-only or unknown.

## CI delivery target

The active frontend model is workbenches. A workbench change should receive:

- workbench registry validation;
- affected workbench tests;
- shared frontend checks only when shared frontend code changes;
- mandatory security, secret scanning and merge-gate checks.

Unrelated Python and legacy LCARS checks should not be required for workbench-only changes. Existing required check names must remain stable until branch protection is independently verified and deliberately updated.

## Acceptance criteria

1. All remaining LCARS references are classified.
2. No LCARS source is deleted without an active-consumer check.
3. Workbench governance checks remain available.
4. CI changes do not silently remove mandatory security or merge protection.
5. No production or VM changes occur.

## Owner decisions recorded

- ARCH-12: not required.
- ARCH-15: not required.
- LCARS retirement: proceed in stages, with source removal only after inventory.

## Disposition decision

**Owner decision:** retain `lcars-portal` as the active deployed workbench application. Do not delete its source tree, systemd unit, Caddy route, build configuration or live workbench/API routes.

The LCARS retirement scope is limited to legacy naming, obsolete documentation and the retired CI workflow. Any future renaming or structural cleanup must be a separate, tested change with deployment review.
