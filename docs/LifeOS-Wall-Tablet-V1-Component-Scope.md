# LifeOS Wall Tablet — V1 Component Scope

**Status:** Advisory / Chief Engineer research pass. Not yet built. All three open Captain decisions from §4 are resolved (§2.5), and voice/capture is elevated to V1 (§2.6) — an implementation mission can be opened.
**Author:** Chief Engineer (USS-TJR-003, Engineering Division)
**Date:** 2026-09-04 (revised three times same day — household/hardware context in §2.4, auth/hub/calendar decisions in §2.5, voice/capture elevation in §2.6)
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
- **Voice — corrected 2026-09-04, verified in code, not just docs.** This doc's first pass conflated two different things. What's actually **dead** is a specific proactive feature, "XO Voice Daily Debrief" (a scheduled unprompted briefing) — that one stays parked per the Registry's existing recommendation to check recoverability before rebuild-vs-retire. What's **live and working today** is a real voice pipeline, verified directly in `telegram-bots/xo/`:
  - **Voice capture (STT → classify → write):** `voice_capture.py` — Telegram voice notes are transcribed via a local `faster-whisper` process (`services/transcription`), classified with deterministic keyword rules into `thing_to_do` / `decision` / `capacity_signal` / `content_idea` / `mission_idea` / `note`, then written into `captured_items` (Captain's Inbox) via the same canonical envelope the portal's own Quick Capture uses. `capacity_signal` captures even auto-promote into `capacity_checkins`. It already has heartbeat monitoring wired in and has `test_voice_capture.py` coverage — this is mature, not a stub.
  - **Voice output (TTS):** `core/voice/tts_edge.py` — Microsoft Edge's cloud TTS (`edge-tts`, no API key), voice `en-AU-WilliamNeural`, used today to send spoken Telegram replies as a "bonus layer" after the text reply, with silent fallback if TTS is unavailable.
  - **Quick Capture itself** is a real, multi-channel, already-built capability, not something this doc previously credited: `lcars-portal/src/lib/capture.ts` defines a canonical envelope and an extensible `KNOWN_CHANNELS` registry (`lcars-mobile-quick-capture`, `telegram-xo-voice-capture`, `telegram-xo-text-capture`, `portal-floating-capture`, `command-centre-api-capture`) writing into the same `captured_items` table, with a portal review UI (`QuickCapture.tsx`, `/capture`) already live.

  Both pieces are Telegram-only today. A wall-tablet voice component is composition, not new-build: add a new `KNOWN_CHANNELS` entry (e.g. `wall-tablet-voice-capture`), reuse `classify_text`/`save_capture`'s logic and `tts_edge.py`'s voice directly, and reuse the existing transcription service rather than re-implementing STT. See §2.6.

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

Sensibo is cloud-API-only regardless of where Home Assistant runs, so aircon control is technically unblocked by the deferred bridge decision on its own — that was this doc's initial read. **The Captain overrode that and moved aircon to V1.1 as well**, alongside lighting: smart-home control ships as one bundle once Home Assistant and its LAN bridge are properly stood up, rather than partially standing up device control for one vendor while the hub's own network story is still unresolved. Both Kasa/Tapo lighting and Sensibo aircon are **V1.1**.

### 2.6 Voice is elevated to a first-class V1 component (Captain's call, 2026-09-04)

The Captain flagged voice as needing "a bigger play" than this doc's first pass gave it. That first pass was wrong to treat voice as one undifferentiated deferred item — §2.1's correction splits it into three concrete pieces, two of which are already live:

- **Text/voice capture on the wall tablet**, reusing the real `captured_items` pipeline directly: a capture bar (type or tap-to-talk) writing through a new `wall-tablet-*` channel, exactly the same envelope Telegram voice capture already writes. This is genuinely composition — the classification rules, the Supabase write, and the review-first flow (nothing auto-executes, everything lands `pending`/`unreviewed` for later review in the existing `/capture` portal page) all already exist.
- **Spoken output for the alert/situation surfaces**, reusing `tts_edge.py`'s existing Australian voice: an emergency alert or a needs-attention item read aloud, not just displayed — genuinely valuable on a wall-mounted device you're not always looking directly at, and it's the same TTS call already proven over Telegram, just a new caller.
- **The still-dead "XO Voice Daily Debrief"** stays exactly where the Registry already put it — untouched by this elevation. Don't fold its recoverability question into this work; if it's ever revived, treat it as separate.

Real engineering, not blocked on anything: the STT half needs a channel-agnostic version of `voice_capture.py`'s pipeline reachable from `lcars-portal` (today it's a Telegram-bot-local subprocess call into `services/transcription` — needs to become a small internal API both Telegram and the wall tablet can call, not two copies of the classification logic). One consequence for §2.5's auth model: the kiosk device identity was scoped **read-only**; capture needs it to also **write** — narrowly, to `captured_items` inserts only, nothing else. Still least-privilege, still revocable, just no longer read-only-in-the literal sense that phrase implied. This is a refinement of the adopted design, not a new escalation — see §3.2 and §4.

### 2.7 Google Calendar integration — technical design (2026-09-04)

Same trust-boundary principle as §2.3's Home Assistant note: **the kiosk never holds Google credentials and never talks to Google directly.** Four pieces:

1. **One-time OAuth connection, done by the Captain, not the kiosk.** A new portal route behind normal Captain login (not the kiosk device identity) starts Google's OAuth consent flow requesting the **read-only** scope (`calendar.readonly`) — no write/modify scope requested, since V1 is display-only (§3.2 item 6). `access_type=offline` + `prompt=consent` ensures Google issues a refresh token, not just a short-lived access token.
2. **Server-side token storage.** The refresh token lands in a new, small Supabase table reachable only via the server-side service role — never exposed to the browser, never readable by the kiosk's own scoped device identity. Same boundary as Home Assistant holding the Kasa/Sensibo secrets instead of the kiosk holding them.
3. **A new internal read endpoint** (e.g. `/api/calendar/today`), server-side only: exchanges the stored refresh token for a short-lived access token, calls the Calendar API for today's events on whichever calendar the Captain designates as "the life calendar," normalizes the result into the same `{time, title, location}` shape the prototype's agenda panel already expects, and caches it ~5 minutes server-side so the kiosk's own polling never hits Google directly.
4. **Kiosk consumption.** The wall tablet calls this endpoint through the exact same scoped device identity already adopted for the situation strip and alerts (§2.5) — one more read-only route behind the existing gate, no new auth model.

**Failure handling:** if the refresh token is revoked or silently expires, the endpoint must return an explicit "Calendar disconnected — reconnect in settings" state, not a silently stale or empty panel — the same stale-data-must-be-visible principle §5 already requires for a dropped Wi-Fi connection.

**Google Cloud setup — done (2026-09-04):** the Captain completed step 1 ahead of the implementation mission — project created, Calendar API enabled, consent screen branded and published **In production** (avoids the 7-day refresh-token expiry that Testing status carries), and a Web application OAuth client created with redirect URI `https://usstjros.vercel.app/api/auth/google-calendar/callback` matching the design above. Client ID and secret are saved outside this repo (password manager) — never committed here. Nothing left on Google's side; the remaining work (the callback route, the Supabase token table, `/api/calendar/today`) is all code, for whenever the implementation mission opens.

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
| Aircon control (Sensibo) | **No** — net-new, via Home Assistant on VPS | **V1.1** — technically unblocked (cloud-only), but Captain chose to bundle it with lighting (§2.5) |
| Lighting control (TP-Link Kasa/Tapo) | **No** — net-new, needs a VPS↔LAN bridge Home Assistant doesn't have yet | **V1.1** — blocked on a bridge decision deferred by the Captain (§2.5) |
| Quick Capture (text) | Yes — `captured_items`, `capture.ts`, live multi-channel pipeline | **Winner** — near-zero build, real value (§2.6) |
| Voice capture (tap-to-talk) | Partial — STT/classify/write pipeline live (Telegram-only) | **Winner** — elevated by Captain, real composition work (§2.6) |
| Spoken alerts (TTS output) | Partial — `tts_edge.py` live (Telegram-only) | **Winner** — elevated by Captain, thin new caller (§2.6) |
| "XO Voice Daily Debrief" | **Dead** — silently regressed, separate feature from the above | Untouched — not part of this elevation (§2.6) |
| Latest brief / ambient intel | Yes — Briefs archive | Strong V1.1 candidate |
| Meal planning / groceries | **No** | **Excluded** — confirmed not wanted, not deferred |
| Chores / routines | **No** | **Excluded** — confirmed not wanted, not deferred |
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

6. **Calendar/schedule panel** — read-only view of Google Calendar (§2.5; the Outlook 365 work calendar is never ingested here). New integration, new small read model — not composition, but now in scope. Technical design (§2.7): the kiosk never touches Google directly, same trust boundary as Home Assistant holding the smart-home vendor secrets.
7. **Capture bar (text + tap-to-talk voice)** — writes into the real `captured_items` pipeline via a new `wall-tablet-*` channel, reusing `capture.ts`'s canonical envelope and (for voice) `voice_capture.py`'s classify/save logic. The voice half needs the transcription pipeline pulled out of its current Telegram-bot-local subprocess call and exposed as a small internal API both channels can call — real work, but composition, not new capability. Elevated to V1 per the Captain's call (§2.6).
8. **Spoken alerts** — reads the active Emergency Alert Hub / needs-attention item aloud using `tts_edge.py`'s existing Australian voice, as a new caller of an already-built TTS path. Elevated to V1 alongside voice capture (§2.6).

**Deferred to V1.1 as one bundle, not excluded:**

9. **Smart-home panel: lighting (Kasa/Tapo) + aircon (Sensibo)**, both via Home Assistant on the Contabo VPS. Aircon is technically unblocked on its own (Sensibo is cloud-API-only, no LAN dependency), but the Captain chose to hold both until Home Assistant's home-LAN bridge is decided (§2.5), rather than half-standing-up smart-home control. Build together once the bridge (VPN / relocate HA / cloud-only) is chosen.

**Untouched, not part of this scope:**

The dead "XO Voice Daily Debrief" stays exactly where the Registry left it — its recoverability question is separate from items 7–8 above and shouldn't be bundled into this mission.

Meal planning, groceries, and chores remain excluded outright per §2.4/§3.1 — not on any version's roadmap unless that changes.

## 4. Next Actions — all three original decisions resolved (§2.5)

1. ~~Captain decision on kiosk auth model~~ — **Resolved, then refined (§2.6):** scoped device identity behind a server-side API, adopted as designed — now also carrying a narrow write scope (`captured_items` inserts only) for capture, not just read.
2. ~~Captain decision on Home Assistant hub~~ — **Resolved:** runs on the existing Contabo VPS. This surfaced a new, narrower open item — see below.
3. ~~Captain decision on calendar provider~~ — **Resolved:** Google Calendar.
4. **Open item, deferred to V1.1 by the Captain's own call, not blocking V1:** how Home Assistant (on the VPS) reaches Kasa/Tapo and Sensibo devices — VPN tunnel, relocate HA locally, or cloud-only fallback. Both lighting and aircon wait on this together.
5. Open the implementation mission: build the kiosk shell first (item 1 in §3.2), against the now-adopted device-identity auth model (read + narrow capture-write), composing the four reuse-winners, then calendar, then capture + spoken alerts. Smart-home is V1.1, not part of this mission.
6. **New prerequisite surfaced by item 7:** extract `voice_capture.py`'s transcribe→classify→save pipeline into a small internal API callable from `lcars-portal`, rather than copying its logic a second time. Telegram voice capture becomes this API's first caller too, not just the wall tablet's — one canonical implementation, per SUOC Principle 5.
7. Leave the dead "XO Voice Daily Debrief" alone — its recoverability is a separate, pre-existing Registry item, not part of this mission.

## 5. Hardware-driven implementation notes (non-binding, for whoever builds §4.5)

- Helio G85 + 4GB RAM is entry-tier silicon: favor server-rendered/SSR-light panels, poll-based refresh (the platform's existing pattern, e.g. `useAlerts`'s 120s default) over heavy websocket fan-out, and avoid animation-heavy re-renders across a 1920×1200 always-on canvas.
- Wi-Fi-only, no cellular fallback: the shell needs a visible "stale data" state (the Emergency Alert Hub's existing per-source crawl-health pattern is a good model) rather than silently freezing on a dropped connection.
- For V1.1's smart-home panel: a Sensibo command routes tablet → USS TJR's kiosk API → Home Assistant on the Contabo VPS → Sensibo's own cloud, three network hops rather than a same-LAN call — the panel will need to show "command sent" vs. "command confirmed" as distinct states rather than assuming an instant round-trip.
- For voice capture: on-device recording on a Helio G85 tablet is fine (audio capture is cheap), but the transcription itself should stay server-side (the existing `faster-whisper` service), not on-device — don't try to run STT locally on kiosk hardware this modest.

---

## Mission Status

**Advisory only.** No code changed. All three original Captain decisions are resolved (§2.5); an implementation mission can now be opened per §4.5, scoped to V1 = kiosk shell, situation strip, emergency alerts, alerts ticker, reminders, calendar, capture bar (text + voice), and spoken alerts. Smart-home (lighting + aircon, bundled) is V1.1, waiting on the HA↔LAN bridge decision. The dead Voice Daily Debrief is explicitly out of scope.
