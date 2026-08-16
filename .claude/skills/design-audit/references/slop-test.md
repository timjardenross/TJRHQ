# Design audit gate list

Adapted from hallmark's 58-gate slop test. Gate numbers preserved from the source for traceability; hallmark-only gates (macrostructure/theme rotation, `.hallmark/log.json`, greenfield hero-enrichment tiering) are dropped since they assume hallmark's own generation pipeline, which LCARS Portal doesn't run. Every remaining gate answer must be **no** to pass.

---

## Visual

1. Is the display font Inter, Roboto, Open Sans, Poppins, Lato, or a system default with no pairing face?
2. Is there a purple-to-blue (or cyan-to-magenta) gradient anywhere — including a `background-clip: text` gradient headline?
3. Is there a 3-equal-column card grid with icon-above-heading tiles?
4. Is any card nested inside another card with no semantic reason?
5. Is any card using a thick coloured left/right side-stripe border?
6. **Hero/panel shape — centred-everything.** Is a hero or top panel `min-height: 100vh`-style with everything centred, with eyebrow, title, lede, and CTA all stacked on the same centred vertical axis?
7. Is pure `#000` or pure `#fff` used as a base colour anywhere it should be tinted toward the app's anchor hue?

## Structural

8. Does the page reuse the generic template (Hero → 3 features → CTA → footer) with no asymmetry or surprise?
9. Are sections separated only by equal whitespace, with no rule, no ornament, no colour shift — every section identical in rhythm?

## Microinteractions

10. Is `transition-all` (or `transition: all`) used anywhere?
11. Is `hover:scale-105` (or any uniform hover-scale) applied across multiple unrelated elements?
12. Are bouncy/overshoot easings (`cubic-bezier(0.34, 1.56, ...)`) used on UI state changes — buttons, modals, tooltips?
13. Does any element have more than one hover effect at the same time (translate + scale + shadow + colour + rotate)?
14. Are you animating `width`, `height`, `top`, `left`, `margin`, or `padding` anywhere?
15. Does the focus ring transition into existence (fade in) instead of appearing instantly?
16. Is there a celebratory success toast for an action whose effect the user can already see?
17. Are tooltip hover-delay and focus-delay equal? (Hover should delay 800–1000ms; focus should be 0ms.)
18. Is auto-rotating content (carousel, banner, stats) lacking pause-on-hover-and-focus? (WCAG 2.2.2.)
19. Is there a placeholder name "Jane Doe / John Smith" or a startup cliché (Acme, Nexus, Seamless, Unleash)?

## Implementation gates

22. Does any neutral/surface colour have `oklch(... 0 ...)` (zero chroma) where the app's design language tints neutrals toward an anchor hue?
23. Does the accent colour cover more than ~5% of any single viewport (solid fills, large headings in accent, full-bleed accent backgrounds)?
24. Is any padding/gap/margin a value that isn't on the app's named spacing scale? Arbitrary `padding: 17px` is a tell.
25. Is any prose container's `max-width` outside the 45–75ch range?
26. Does any interactive element lack `:focus-visible`, `:active`, or `:disabled` styling?
27. Is there any `transform`/`animation` keyframe not covered by a `@media (prefers-reduced-motion: reduce)` fallback?

## Icon discipline

30. **Icon tells.** Does the page mix two or more icon libraries on the same page, OR use an emoji glyph (✨ 🚀 ⚡ 🔥 🎯 ✅) as a feature/value-prop/step/status icon?

## Accessibility

33. Does any visual-only `<svg>`, custom-art `<div>`, `<canvas>`, or decorative figure lack `aria-label` or `aria-hidden="true"`?

## Layout-safety gates

34. Does the page horizontally scroll on any viewport between 320px and 1920px? Required fix: `overflow-x: clip` on both `html` and `body` — `clip`, not `hidden`.
35. For every decorative effect on text (highlighter `<mark>`, accent stroke, underline) — is the position/size visually confirmed correct (not reading as a fat baseline underline)?
36. Are interactive bars (nav, toolbar, command bar, CTA row, footer link strip) explicitly vertically centered (`align-items: center` + `line-height: 1` on mixed-height siblings)?

## Typography discipline gates

37. Does the page use more than three distinct `font-family` families?
38. Is the outlier/display face used in more than two slots on the page?
38a. Is any heading or display type italic (`font-style: italic` on `h1`–`h6`, a title class, a stat figure, or an `<em>`/`<i>` inside a heading)? Headers must be roman; carry emphasis with weight, accent colour, or a drawn underline.

## Input-state gate

39. Do input/textarea/select fields handle every state correctly? Fail on any of:
    - Border-width shifts between states (must stay constant; state changes go to background/outline/box-shadow/border-color).
    - Focus ring built from `border` instead of `outline`.
    - Input height ≠ adjacent button height on the same form.
    - Helper-text slot collapses when empty (reserve `min-height: 1lh`).
    - Disabled signalled by `opacity` alone (needs `opacity` + `cursor: not-allowed` + `disabled`/`aria-disabled`).

## Contrast & readability

Universal — the highest-value gates for LCARS given known WCAG history.

40. **Contrast thresholds.** For every `(color, background-color)` pair, verify: body text (under 24px regular / under 18px bold) needs WCAG 4.5:1 / APCA Lc ≥ 60; large text (≥24px regular / ≥18px bold), icons, and focus rings need WCAG 3:1 / APCA Lc ≥ 45. OKLCH pre-check: if `|L_text − L_bg| < 50%`, the pair likely fails — confirm with full calculation.
41. **The contrast failures that ship most often.** Fail on any:
    - Button text ≈ button fill (within 5% lightness AND 0.05 chroma in OKLCH) — the black-on-black bug.
    - Accent-on-accent-fill missing a defined ink token, or that ink token failing ≥4.5:1 against the fill.
    - Dark-section ink-on-ink — any panel with `background-color` lightness < 50% must also swap its text colour and ensure nested children inherit it.

## Nav / footer / structural chrome

42. **Nav fingerprint.** Is the nav the generic default — wordmark-left + 4–5 inline links + button-right, full width, 1px hairline border-bottom, white background — used indiscriminately across pages that should differ by function/department?
43. **Footer fingerprint.** Is the footer a generic 4-column link block + social row + tiny copyright with no relevance to an internal tool's actual needs?
44. **Fold fit.** On a standard viewport (test 1280×800), can the panel's essential content (heading, primary actions, key data) be seen without scrolling? Usual culprits: oversized display clamp, loose line-height, bloated padding.
45. **Decorative-without-purpose.** Does a panel contain a decorative element (gradient blob, abstract shape, badge) with no semantic anchor in the content?

## Honest data — no fabricated content

Highest-priority gate for LCARS given the known live+mock data mixing on dashboards.

46. **Invented or unlabeled data.** Does the page contain any quantitative claim, metric, or status that is mock/placeholder data displayed without a visible "mock"/"demo"/"pending" label, or presented indistinguishably from live data? If a metric can't be sourced live, it must carry a `—` + labelled placeholder, or the section is rebuilt without the slot. This directly targets the dashboard-mixes-live+mock-data pattern already found in this app.

## Re-drawn UI chrome

47. Did the page hand-build a fake browser bar, fake phone frame, fake terminal/IDE chrome using HTML/CSS/SVG instead of a real screenshot or the actual chrome the environment provides?

## Token discipline

48. **Mid-render token improvisation.** Does the artifact contain any inline colour value (`#hex`, `oklch(...)`, `rgb(...)`) or `font-family` declaration outside the app's defined design tokens? Every colour/font should reference a named token.

## Responsive — clickable affordances

49. Does any button label, primary nav link, footer link, tab label, breadcrumb, or CTA text wrap to two or more lines at any viewport between 320px and 1920px?

## Mobile-responsiveness non-negotiables

Given the known 1024–1279px dead zone and near-total lack of mobile nav across workbenches, these gates carry real weight here — verify at 320/375/414/768/1024/1280px.

50. Does any `grid-template-columns`/`grid-template-rows` containing a `1fr` track render an image-bearing element inside that track without `minmax(0, 1fr)`?
51. Does any display-size heading lack `overflow-wrap: anywhere; min-width: 0`, risking overflow on long words/compound names?
52. Does a component override its section-head grid to a non-`1fr` layout without a matching mobile-collapse rule at `max-width: 48rem`?
53. Does a CSS-only radio-tab pattern scroll-jump on click (position:absolute radios with no JS guard)?
54. Does any section render an eyebrow/label/number beside its heading in a two-column layout, instead of stacked vertically in one column?
55. Does an all-caps display heading combine `text-transform: uppercase` with `line-height` below 1.0 (risking cap-collision on wrap)?
56. Is there more than one `position: sticky; top: 0` element on the page (a nav plus another sticky element both pinned to the viewport top with no offset)?

---

If any answer is **yes**, it's a finding. Report it — do not fix it (see SKILL.md § What this skill does NOT do).
