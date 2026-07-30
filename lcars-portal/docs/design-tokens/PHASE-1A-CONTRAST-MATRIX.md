# Phase 1A — Token Consolidation & Contrast Matrix

**Mission:** USS-TJR-MSN-0315, Phase 1A (Foundation)
**Origin:** `Missions/Active/CAPTAIN-EXPERIENCE-IMPLEMENTATION-ROADMAP.md` Phase 1, executing MSN-0310 §4.2's prescribed token consolidation
**Scope:** Token layer only. No component code changed.

---

## 1. What changed

Added an independent `state` colour token group to `lcars-portal/tailwind.config.ts` (`state.ok/warn/crit/unknown`, each with `DEFAULT`/`soft`/`on`), reviving the ratified rule that operational status is never overridden by department identity colour (`archive/lcars-portal-migration-2026-06/command-centre/STARFLEET-DESIGN-STANDARD.md` §2, rule 5; §10, rule 3 — carried forward as the prescribed fix in MSN-0310 §4.2).

The existing `status` department-shaped token (Status Green) is untouched — it remains in use by current consumers (`StatusBadge`, `departments.ts`). Migrating those consumers onto the new independent `state` tokens is **Phase 1B** work (Health/Status Indicator + Data Source Indicator formalization, per MSN-0310 §6), not done here.

No hex value of any existing department token (`command`, `engineering`, `operations`, `medical`, `science`, `status`) was changed. Those are Design System v1.0, ratified by Captain in MSN-0310 — changing them is a Visual Design Officer call, not an engineering one.

---

## 2. Contrast validation method

WCAG 2.2 relative-luminance contrast ratios, computed directly (not eyeballed), against all three live backgrounds: `space` (`#dce8f4`), `panel` (`#eaf1f8`), `panel-2` (`#ccd8ec`). Thresholds: `DEFAULT` values (used as solid fills — dots, borders, icons) need ≥3:1 (WCAG AA, graphical objects/large text); `on` values (used as body text on light backgrounds) need ≥4.5:1 (WCAG AA, body text). These are the exact thresholds MSN-0310 §4.3 / the archived standard §8 specify.

---

## 3. Results — existing department tokens (unchanged, informational)

**`DEFAULT` (need ≥3:1) vs. backgrounds:**

| Token | Hex | space | panel | panel-2 | Result |
|---|---|---|---|---|---|
| command | `#FFB81C` | 1.39 | 1.52 | 1.20 | **FAIL** |
| engineering | `#FF9800` | 1.73 | 1.89 | 1.50 | **FAIL** |
| operations | `#F44336` | 2.96 | 3.23 | 2.56 | **FAIL** |
| medical | `#0099FF` | 2.41 | 2.63 | 2.09 | **FAIL** |
| science | `#CC88FF` | 1.98 | 2.16 | 1.71 | **FAIL** |
| status (legacy) | `#4CAF50` | 2.24 | 2.44 | 1.93 | **FAIL** |

**`on` (need ≥4.5:1) vs. backgrounds:**

| Token | Hex | space | panel | panel-2 | Result |
|---|---|---|---|---|---|
| command | `#7A4D00` | 5.85 | 6.38 | 5.05 | PASS |
| engineering | `#8A3C00` | 6.19 | 6.76 | 5.35 | PASS |
| operations | `#B71C1C` | 5.28 | 5.77 | 4.57 | PASS |
| medical | `#005299` | 6.33 | 6.91 | 5.47 | PASS |
| science | `#5B2AAA` | 7.17 | 7.82 | 6.20 | PASS |
| status (legacy) | `#1B5E20` | 6.33 | 6.91 | 5.47 | PASS |

### Flag for Design Officer / Visual Design Officer review

**None of the six ratified department `DEFAULT` colours meet the 3:1 minimum against any live background.** This is broader than the two colour-pairs MSN-0310 §4.2 flagged as "at risk of collapsing for colourblind users" — those two pairs are also individually failing the plain AA bar, for every department, regardless of colour vision. Likely cause: these hex values were carried over from a design intended for use as solid fills behind white/dark text (buttons, dark-theme chips), not as small standalone graphical indicators (status dots, thin borders) directly against the light `space`/`panel` backgrounds.

This is **not fixed in Phase 1A** — changing ratified brand hex values is a Visual Design Officer call, not an engineering one. Two acceptable paths exist, both deferred to Phase 1B/1C component work (Health/Status Indicator, Data Source Indicator formalization) rather than decided here:
1. Component-level mitigation: pair the solid dot with an `on`-coloured outline/ring (already well above 4.5:1), satisfying the ratified Colour+Shape+Label rule without touching the brand hex.
2. Visual Design Officer revises the `DEFAULT` shades specifically for their use as standalone light-background indicators (a new `on-light-indicator` variant, or a shade adjustment), reviewed and ratified through the existing Design Governance Model (MSN-0310 §9) before any component consumes it.

The `on` variants are unaffected and already comfortably pass everywhere they're used as text.

---

## 4. Results — new `state` tokens (Phase 1A, contrast-validated by construction)

**`DEFAULT` (need ≥3:1):**

| Token | Hex | space | panel | panel-2 | Result |
|---|---|---|---|---|---|
| state.ok | `#278A44` | 3.52 | 3.84 | 3.04 | PASS |
| state.warn | `#9C5D10` | 4.24 | 4.62 | 3.66 | PASS |
| state.crit | `#C43030` | 4.43 | 4.84 | 3.83 | PASS |
| state.unknown | `#5A6690` | 4.52 | 4.93 | 3.91 | PASS |

**`on` (need ≥4.5:1):**

| Token | Hex | space | panel | panel-2 | Result |
|---|---|---|---|---|---|
| state.ok | `#1B5E20` | 6.33 | 6.91 | 5.47 | PASS |
| state.warn | `#7A4610` | 6.23 | 6.80 | 5.39 | PASS |
| state.crit | `#7A1616` | 8.65 | 9.44 | 7.47 | PASS |
| state.unknown | `#33395C` | 8.98 | 9.80 | 7.76 | PASS |

All four `state` tokens pass at every live background, at both the fill and text usage tiers, with margin.

---

## 5. Colour-blind consideration

The archived standard's colour-blind mode (`data-colorblind="true"` remap table, `STARFLEET-DESIGN-STANDARD.md` §8) is **not implemented in this phase** — it requires a preference-toggle mechanism that does not exist yet in `lcars-portal` (no consumer to wire it to would mean dead CSS). Recorded here as a known, deferred item for whichever phase introduces a Preference Manager (Phase 2/3 per the roadmap), not invented speculatively now.

In the meantime, the ratified Colour+Shape+Label rule (MSN-0310 §4.3, rule 1) remains the operative mitigation: no component may use `state` or department colour as the sole indicator of meaning — every status/department indicator must also carry an icon/shape or text label. This is enforced at the component layer (Phase 1B), not the token layer.

---

## 6. Validation performed

- Contrast ratios computed via WCAG 2.2 relative-luminance formula (script-computed, not visual estimate).
- `npx tsc --noEmit` against `tailwind.config.ts` — type-checks clean.
- `tailwindcss` CLI ran against the updated config with a probe file referencing `bg-state-ok`, `text-state-ok-on`, `border-state-crit`, `bg-state-warn/15`, `text-state-unknown-on` — all 5 utility classes generated correctly, confirming the new token group compiles into real, usable Tailwind utilities.
- No component files touched; `git diff --stat` limited to `tailwind.config.ts` + this doc.

## 7. Rollback

Purely additive change (`state` block + comment in `tailwind.config.ts`, this doc). No existing token renamed, removed, or revalued; no component imports the new tokens yet. A single `git revert` of the Phase 1A commit fully restores prior state with zero blast radius.
