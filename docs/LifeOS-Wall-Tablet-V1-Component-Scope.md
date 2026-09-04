# LifeOS Wall Tablet — V1 Component Scope

**Status:** Advisory / Chief Engineer research pass. Not yet built. Needs Captain decision on the auth-model question in §4 before any implementation mission is opened.
**Author:** Chief Engineer (USS-TJR-003, Engineering Division)
**Date:** 2026-09-04
**Target hardware:** Lenovo Tab (ZAEH0138AU) — 10.1" 1920×1200 IPS, MediaTek Helio G85, 4GB RAM, 128GB storage, 5100mAh, Wi-Fi only, Android. Budget/entry silicon and RAM headroom — this constrains the technical approach (§5), not just the component list.

---

## 1. Mission Summary

Research what a wall-mounted "LifeOS" tablet should show, working wide-to-narrow: survey the full space of plausible glanceable-dashboard components, then identify which are genuine V1 winners versus later work — grounded in what USS TJR already has built (the 12 live workbenches, the SUOC Platform Registry's capability inventory, and the existing Mobile Command MVP), not built from a blank slate.

## 2. Assessment

### 2.1 What already exists that a wall tablet can compose onto directly

This platform runs on a reuse-before-rebuild principle (SUOC Principle 3, ADR-020), and there's real prior art for exactly this shape of surface:

- **`platform-runtime`/`lcars-portal` Mobile Command MVP (MSN-IOS-001)** is the closest precedent — a PWA-first, zero-new-backend mobile surface (`docs/MOBILE-MVP.md`) with a Push Alerts view (`useAlerts.ts`) that polls a "gated alert engine" aggregating 6 alert sources and fires Web Notifications on new critical/high alerts only. Its Captain's Chair card stack (`MobileOperatingPicture`) is a directly relevant precedent for "glanceable situation" layout, **but** the Captain's Chair workbench page comment records that `MobileOperatingPicture` and its supporting hooks (`command-centre.ts`, `useCommandCentre.ts`) were **retired outright on 2026-08-29** with "no real alternate path back." So the *pattern* is proven; the specific component is dead code — don't resurrect it, rebuild the pattern fresh per that page's own note.
- **Emergency Alert Hub Workbench** (`/emergency-alert-hub-workbench`) is close to ideal ready-made content for a wall display: Tier‑1 official AU emergency alerts (NSW/VIC/QLD/SA/ACT), jurisdiction/severity filters, per-source crawl health. This is the single highest-value, lowest-effort panel available — it's a safety surface, already built, already gated through hardened RLS.
- **Human Systems Workbench** (`/human-systems-workbench`) is first-party recovery/capacity telemetry (`capacity_checkins`, recovery posture, capacity state) with a live Supabase realtime subscription already wired (`useRealtimeRefresh` on `capacity_checkins`). This is the natural source for a "how's today going" glanceable tile.
- **Captain's Chair's Situation Strip** (recovery posture band, capacity state, health severity — `POSTURE_STATE_TONE`/`RISK_STATE_TONE`/`CAPACITY_STATE_LABEL` in `captains-chair-workbench/page.tsx`) is exactly the kind of compact status-badge row a wall display wants, and the tone-mapping logic is already centralized in `lib/departments.ts` (`stateToneClasses`, `alertSeverityToTone`, `capacityStateToTone`, `healthSeverityToTone`) — reusable without touching the source page.
- **Briefs** (`/briefs`) — the synthesized intelligence-brief archive — is a plausible source for a rotating "latest brief" ambient panel, low build cost.
- **Notification capability** (`core/platform/notification_service.py`) exists, is validated standalone, but per the Platform Registry is **Dormant — zero production callers** (CMDB Status: Dormant, Risk: Low, Recommendation: Fix Later, pending a `command_bus.py` cutover held). A wall-tablet reminder/nudge ticker would be a genuine first production consumer of already-built infrastructure rather than new capability — a good use of existing debt rather than a new one.
- **Voice** — `core/voice/tts_edge.py` (text-to-speech) exists, but the Registry records "XO Voice Daily Debrief" as **silently regressed to fully dead**, with the explicit recommendation to check recoverability before deciding rebuild-vs-retire. Any voice component here inherits that unresolved question — not a clean V1 add.

### 2.2 What genuinely doesn't exist (real gaps, not just unwired UI)

- **No calendar/schedule capability anywhere in the platform.** Grepped `lcars-portal` and `core` for calendar/family/grocery/chore/meal-plan/routine — the only hits are unrelated (`mission-workbench`, `contentScoring.ts`). "What's on today" is arguably the single most-expected wall-tablet widget and it would be net-new integration work (a calendar source — Google Calendar/CalDAV/etc. — plus a new read model), not composition.
- **No household/family multi-user model.** The platform's governance is Captain-singular by design (SUOC Principle 9, "Captain Intelligence Is Composed, Not Implemented"; RLS policies are keyed to a single authenticated identity — see the `advisory_sessions`/`health_daily_logs` anon-RLS incidents already fixed in 2026-07-18, which is exactly the failure mode a shared-household surface risks reintroducing if rushed). Turning this into "the family's" tablet is an identity/authorization model change, not a UI feature.
- **No smart-home/IoT integration** (lights, locks, thermostat) anywhere in the registry.
- **No meal planning, grocery list, or chores/routines data model.**
- **No existing kiosk/wall-display/always-on presentation mode.** Every UI surface in the platform — including the Mobile Command MVP — sits behind full Supabase-authenticated middleware (`lcars-portal/src/middleware.ts`: any unauthenticated request to a non-allowlisted route redirects to `/login`). There is no precedent for a screen that stays open and logged in indefinitely in a physically shared space.

### 2.3 Security note (flagging per Chief Engineer escalation duty, not deciding it)

A wall tablet is a different threat model from a phone in a pocket: it's a browser session that must stay authenticated 24/7, physically walk-up-accessible to anyone in the house (and to anyone who can see the screen). The existing `BOT_API_SECRET` bypass in `middleware.ts` is explicitly scoped to `/api/*` server-to-server calls "so a leaked/shared bot secret grants programmatic access only, not full authenticated-UI browsing" — reusing that pattern for a client-rendered kiosk page would undo that exact protection and should not be done. This repo has twice shipped and fixed real RLS/anon-read exposures on sensitive tables (`advisory_sessions`, `health_daily_logs`) — a new always-on unauthenticated-feeling surface is precisely the shape of thing that produces a third. **This is a platform-wide, shared-middleware decision and belongs to the Captain, not something to design around unilaterally** (see §4).

## 3. Recommendations

### 3.1 Wide scan — every plausible component, scored

| Component | Exists today? | V1 fit |
|---|---|---|
| Situation strip (recovery posture / capacity / health severity) | Yes — Captain's Chair logic, reusable tone-mapping | **Winner** |
| Emergency/safety alerts (Tier‑1 AU) | Yes — Emergency Alert Hub Workbench | **Winner** |
| Needs-attention / alerts ticker | Yes — `useAlerts` + gated alert engine | **Winner** |
| Reminders / nudges | Partial — Notification service built, dormant | **Winner** (activates existing debt) |
| Latest brief / ambient intel | Yes — Briefs archive | Strong V1.1 candidate |
| Today's calendar/schedule | **No** — no capability exists | Deferred — real new-build |
| Family/household shared view | **No** — Captain-singular governance model | Deferred — architecture decision, not UI |
| Meal planning / groceries | **No** | Deferred |
| Chores / routines | **No** | Deferred |
| Smart home controls | **No** | Out of scope — security-sensitive, no integration exists |
| Voice interaction | Partial — TTS only, prior voice feature dead | Deferred — root-cause the dead feature first |
| Weather | **No** | Cheap standalone add, not platform-dependent — low priority filler |
| Ambient photo mode | **No** | Trivial, zero platform risk — nice-to-have filler, not a "component" |
| Agent/job platform health | Yes — Agent & Job Status Workbench | Cut from V1 — ops-facing, not household-facing |
| Content/Advisory/OSINT workbenches | Yes | Cut from V1 — desktop workflows, not glanceable |

### 3.2 Recommended V1 scope (the actual winners)

1. **Kiosk display shell** (new, foundational — see §4 for the auth blocker this depends on) — a dedicated always-on route, no interactive chrome, auto-cycling panels, large type, screen-timeout-safe.
2. **Situation strip** — recovery posture, capacity state, health severity — reusing `lib/departments.ts` tone-mapping, not the retired `MobileOperatingPicture`.
3. **Emergency Alert Hub panel** — near-zero build cost, highest safety value, already hardened.
4. **Alerts/needs-attention ticker** — thin wrapper over the existing `useAlerts` hook.
5. **Reminder/nudge ticker** — first production caller of the dormant Notification capability.

Everything else in §3.1 is deliberately **not** V1: calendar and family/household are the two components a household member will most expect and are also the two with zero existing platform support — they're the right V1.1 target once the kiosk shell and its auth model exist, not something to bolt on now.

## 4. Next Actions

1. **Captain decision required before any build:** how does an always-on wall device authenticate? Options to weigh (not pre-decided here): a scoped, revocable device/kiosk identity with least-privilege RLS behind a dedicated server-side read API; vs. a long-lived kiosk-specific session cookie; vs. something else. This is a shared-middleware, platform-wide change per SUOC governance and Chief Engineer escalation rules — it does not get decided inside a component-scope doc.
2. Once the auth model is set: open a mission to build the kiosk shell as its own thin route, composing the four reuse-winners in §3.2 — no new backend capability needed for V1.
3. Defer calendar and household/family-model work to a V1.1 mission scope once the shell exists and the auth pattern is proven.
4. Before touching voice: check recoverability of the dead XO Voice Daily Debrief feature per the Registry's existing open item, rather than starting a parallel voice effort.

## 5. Hardware-driven implementation notes (non-binding, for whoever builds §4.2)

- Helio G85 + 4GB RAM is entry-tier silicon: favor server-rendered/SSR-light panels, poll-based refresh (the platform's existing pattern, e.g. `useAlerts`'s 120s default) over heavy websocket fan-out, and avoid animation-heavy re-renders across a 1920×1200 always-on canvas.
- Wi-Fi-only, no cellular fallback: the shell needs a visible "stale data" state (the Emergency Alert Hub's existing per-source crawl-health pattern is a good model) rather than silently freezing on a dropped connection.

---

## Mission Status

**Advisory only.** No code changed. Blocked on Captain decision (§4.1) before an implementation mission can be opened.
