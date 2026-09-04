# LifeOS Wall Tablet — V1 Component Scope

**Status:** Advisory / Chief Engineer research pass. Not yet built. All three open Captain decisions from §4 are now resolved (see §2.5) — an implementation mission can be opened.
**Author:** Chief Engineer (USS-TJR-003, Engineering Division)
**Date:** 2026-09-04 (revised twice same day — household/hardware context in §2.4, then auth/hub/calendar decisions in §2.5)
**Target hardware:** Lenovo Tab (ZAEH0138AU) — 10.1" 1920×1200 IPS, MediaTek Helio G85, 4GB RAM, 128GB storage, 5100mAh, Wi-Fi only, Android. Budget/entry silicon and RAM headroom — this constrains the technical approach (§5), not just the component list.
**Household:** Single-person household plus one dog. No multiple residents, no shared-custody access model.

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

- **No calendar/schedule capability anywhere in the platform.** Grepped `lcars-portal` and `core` for calendar/family/grocery/chore/meal-plan/routine — the only hits are unrelated (`mission-workbench`, `contentScoring.ts`). "What's on today" is arguably the single most-expected wall-tablet widget and it would be net-new integration work (a calendar source plus a new read model), not composition. **Now confirmed in scope for V1** — see §2.4.
- **No smart-home/IoT integration** (lights, locks, thermostat, aircon) anywhere in the registry. **Now confirmed in scope for V1** (lighting + aircon only) — see §2.4.
- **No meal planning, grocery list, or chores/routines data model.** **Confirmed explicitly out of scope** by the Captain (single-person household, this admin overhead isn't wanted) — not deferred, excluded.
- **No existing kiosk/wall-display/always-on presentation mode.** Every UI surface in the platform — including the Mobile Command MVP — sits behind full Supabase-authenticated middleware (`lcars-portal/src/middleware.ts`: any unauthenticated request to a non-allowlisted route redirects to `/login`). There is no precedent for a screen that stays open and logged in indefinitely in a physically shared space.

### 2.4 Household context and hardware confirmed by the Captain (2026-09-04)

The original wide scan (§2.1–2.2) flagged a household/family multi-user model as a real architectural gap. That gap **doesn't apply here**: this is a single-person household plus a dog, no shared-custody or multi-resident access model — which is exactly what the platform's existing Captain-singular governance (SUOC Principle 9) already assumes. Nothing about identity/authorization needs to change; the kiosk-auth question in §2.3/§4 is about *device* security (a screen physically present in the home), not about supporting multiple distinct household identities.

Three further specifics that change the V1 scope directly:

- **Lighting:** TP-Link Kasa/Tapo. No existing platform integration; well-supported by Home Assistant's `python-kasa`-based integration, largely local-network control (no cloud round-trip needed for on/off/brightness on most Kasa devices; some newer Tapo devices are cloud-dependent).
- **Aircon:** Sensibo — a WiFi retrofit AC controller (IR-based, works regardless of the underlying aircon brand). Cloud-API only; no local control path. Well-supported by Home Assistant's official Sensibo integration.
- **Hub:** No smart-home hub exists yet. Standing up **Home Assistant** as a local aggregation layer is the reuse-first answer here, for the same reason the platform favors one canonical implementation per capability elsewhere (SUOC Principle 5): one integration point for Kasa/Tapo + Sensibo (and whatever gets added later) instead of USS TJR/Supabase talking to two-plus vendor clouds directly and holding their credentials. This is net-new local infrastructure (not an existing USS TJR capability) and needs to be stood up before any wall-tablet smart-home panel can work — see §4.
- **Calendar:** No single existing "life calendar" — currently split across providers, and the Outlook 365 **work** calendar is explicitly excluded from this surface (enterprise account, not to be pulled into a personal wall display). The Captain is open to consolidating personal scheduling onto one calendar to be the canonical source. **Recommendation: Google Calendar** — REST API + OAuth is the lowest-friction integration path for a read-only wall display (versus CalDAV for iCloud), and it can still absorb subscribed feeds (e.g. public holidays) without extra integration work. Final pick is the Captain's call, not pre-decided here.

### 2.5 The three §4 decisions, resolved (2026-09-04)

- **Kiosk auth model:** Captain deferred to the Chief Engineer recommendation — **scoped, revocable device/kiosk identity with least-privilege RLS behind a dedicated server-side read-only API**, not a long-lived session cookie carrying the Captain's own full access. This is now the adopted design, not just the recommended one.
- **Calendar provider:** **Google Calendar**, confirmed.
- **Home Assistant host:** the Captain's existing always-on machine is a **Contabo VPS**, not local hardware. This changes the picture from §2.4's assumption of a local box: **Home Assistant on a VPS cannot reach Kasa/Tapo devices on the home LAN directly** — local device discovery/control doesn't cross the WAN. Three options were put to the Captain (a VPN tunnel between the VPS and home network; moving HA to a small local device instead; or cloud-only control on the VPS as-is) and the Captain deferred that specific bridging decision to **V1.1**, rather than picking now.

That deferral has a direct, asymmetric scope consequence, not a symmetric one:

- **Sensibo (aircon) is cloud-API-only regardless of where Home Assistant runs** — it has no local control path at all (§2.4). So Home Assistant-on-the-Contabo-VPS controlling Sensibo is **fully unblocked today**, independent of the deferred bridge decision. Aircon — which the Captain flagged as important — **stays in V1**.
- **Kasa/Tapo (lighting) local control depends on exactly the bridge question that was deferred.** Building it now would mean guessing an architecture (VPN vs. relocate HA vs. cloud-only) the Captain explicitly chose not to lock in yet. **Lighting moves to V1.1**, to be built once the bridge is chosen — this isn't a downgrade in importance, it's sequencing around a real open dependency rather than building on a guess.

### 2.3 Security note (flagging per Chief Engineer escalation duty, not deciding it)

A wall tablet is still a different threat model from a phone in a pocket, single-occupant household or not: it's a browser session that must stay authenticated 24/7, physically accessible to anyone who is ever in the house (guests, tradespeople, a future change in household) or who can see the screen from outside a window. The existing `BOT_API_SECRET` bypass in `middleware.ts` is explicitly scoped to `/api/*` server-to-server calls "so a leaked/shared bot secret grants programmatic access only, not full authenticated-UI browsing" — reusing that pattern for a client-rendered kiosk page would undo that exact protection and should not be done. This repo has twice shipped and fixed real RLS/anon-read exposures on sensitive tables (`advisory_sessions`, `health_daily_logs`) — a new always-on unauthenticated-feeling surface is precisely the shape of thing that produces a third. **This is a platform-wide, shared-middleware decision and belongs to the Captain, not something to design around unilaterally** (see §4).

The same reasoning applies to the new Home Assistant hub in §2.4: vendor cloud credentials for Kasa/Tapo and Sensibo should live in Home Assistant's own credential store, not in USS TJR's Supabase — keep the wall tablet's control surface a thin authenticated call to HA's local API, not a place that holds smart-home vendor secrets itself. Don't repeat the anon-RLS mistake by giving a new device-facing surface broader data access than it needs.

## 3. Recommendations

### 3.1 Wide scan — every plausible component, scored

| Component | Exists today? | V1 fit |
|---|---|---|
| Situation strip (recovery posture / capacity / health severity) | Yes — Captain's Chair logic, reusable tone-mapping | **Winner** |
| Emergency/safety alerts (Tier‑1 AU) | Yes — Emergency Alert Hub Workbench | **Winner** |
| Needs-attention / alerts ticker | Yes — `useAlerts` + gated alert engine | **Winner** |
| Reminders / nudges | Partial — Notification service built, dormant | **Winner** (activates existing debt) |
| Today's calendar/schedule | **No** — net-new, single-source | **Winner** — Google Calendar confirmed (§2.5) |
| Aircon control (Sensibo) | **No** — net-new, via Home Assistant on VPS | **Winner** — cloud-only, unblocked regardless of LAN bridge (§2.5), "important" per Captain |
| Lighting control (TP-Link Kasa/Tapo) | **No** — net-new, needs a VPS↔LAN bridge Home Assistant doesn't have yet | **V1.1** — blocked on a bridge decision deferred by the Captain (§2.5), not a priority downgrade |
| Latest brief / ambient intel | Yes — Briefs archive | Strong V1.1 candidate |
| Meal planning / groceries | **No** | **Excluded** — confirmed not wanted, not deferred |
| Chores / routines | **No** | **Excluded** — confirmed not wanted, not deferred |
| Voice interaction | Partial — TTS only, prior voice feature dead | Deferred — root-cause the dead feature first |
| Weather | **No** | Cheap standalone add, not platform-dependent — low priority filler |
| Ambient photo mode | **No** | Trivial, zero platform risk — nice-to-have filler, not a "component" |
| Agent/job platform health | Yes — Agent & Job Status Workbench | Cut from V1 — ops-facing, not household-facing |
| Content/Advisory/OSINT workbenches | Yes | Cut from V1 — desktop workflows, not glanceable |

### 3.2 Recommended V1 scope (the actual winners)

**Composed from existing USS TJR capability — no new backend needed beyond the kiosk shell itself:**

1. **Kiosk display shell** (new, foundational — see §4 for the auth blocker this depends on) — a dedicated always-on route, no interactive chrome, auto-cycling panels, large type, screen-timeout-safe.
2. **Situation strip** — recovery posture, capacity state, health severity — reusing `lib/departments.ts` tone-mapping, not the retired `MobileOperatingPicture`.
3. **Emergency Alert Hub panel** — near-zero build cost, highest safety value, already hardened.
4. **Alerts/needs-attention ticker** — thin wrapper over the existing `useAlerts` hook.
5. **Reminder/nudge ticker** — first production caller of the dormant Notification capability.

**Net-new for this household, confirmed valuable — real build effort, sequenced after the shell exists:**

6. **Calendar/schedule panel** — read-only view of Google Calendar (§2.5; the Outlook 365 work calendar is never ingested here). New integration, new small read model — not composition, but now in scope.
7. **Aircon panel (Sensibo)** — routed through Home Assistant on the Contabo VPS (§2.5) rather than USS TJR holding Sensibo's cloud credentials directly. Cloud-API-only device, so this has no dependency on the deferred LAN-bridge decision — fully buildable in V1. Flagged as important by the Captain, so sequence it alongside the calendar panel, not after it.

**Deferred to V1.1, not excluded:**

8. **Lighting panel (Kasa/Tapo)** — blocked on the Home Assistant VPS↔home-LAN bridge decision the Captain deferred (§2.5: VPN tunnel vs. relocating HA locally vs. cloud-only fallback). Build this once that's chosen, not on a guessed architecture.

Meal planning, groceries, and chores remain excluded outright per §2.4/§3.1 — not on any version's roadmap unless that changes.

## 4. Next Actions — all three original decisions resolved (§2.5)

1. ~~Captain decision on kiosk auth model~~ — **Resolved:** scoped device identity + read-only server-side API, adopted as designed.
2. ~~Captain decision on Home Assistant hub~~ — **Resolved:** runs on the existing Contabo VPS. This surfaced a new, narrower open item — see below.
3. ~~Captain decision on calendar provider~~ — **Resolved:** Google Calendar.
4. **New open item, deferred to V1.1 by the Captain's own call, not blocking V1:** how Home Assistant (on the VPS) reaches Kasa/Tapo devices on the home LAN — VPN tunnel, relocate HA locally, or cloud-only fallback. Revisit when lighting control is scheduled.
5. Open the implementation mission: build the kiosk shell first (item 1 in §3.2), against the now-adopted device-identity auth model, composing the four remaining reuse-winners, then the calendar panel, then the Sensibo/Home Assistant aircon panel.
6. Before touching voice: check recoverability of the dead XO Voice Daily Debrief feature per the Registry's existing open item, rather than starting a parallel voice effort.

## 5. Hardware-driven implementation notes (non-binding, for whoever builds §4.5)

- Helio G85 + 4GB RAM is entry-tier silicon: favor server-rendered/SSR-light panels, poll-based refresh (the platform's existing pattern, e.g. `useAlerts`'s 120s default) over heavy websocket fan-out, and avoid animation-heavy re-renders across a 1920×1200 always-on canvas.
- Wi-Fi-only, no cellular fallback: the shell needs a visible "stale data" state (the Emergency Alert Hub's existing per-source crawl-health pattern is a good model) rather than silently freezing on a dropped connection. This applies doubly to the aircon panel — a Sensibo command now routes tablet → USS TJR's kiosk API → Home Assistant on the Contabo VPS → Sensibo's own cloud, three network hops rather than a same-LAN call, so the panel needs to show "command sent" vs. "command confirmed" as distinct states rather than assuming an instant round-trip.

---

## Mission Status

**Advisory only.** No code changed. All three original Captain decisions are resolved (§2.5); an implementation mission can now be opened per §4.5. One narrower item (the HA↔LAN bridge) is intentionally deferred to V1.1 and doesn't block V1.
