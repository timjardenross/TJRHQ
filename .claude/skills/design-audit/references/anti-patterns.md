# Anti-patterns — the named tells

Adapted from hallmark's anti-pattern catalog. Two hallmark-only entries (Default-attractor sameness, Specimen fall-through) were dropped — they assume hallmark's own macrostructure-rotation machinery, which has no equivalent in this app. Everything below is a named signature of AI-generated or drifted UI. Seeing one is a problem; seeing two in the same view is a confirmation.

Each entry: the tell, why it reads as AI-generated/drifted, and the fix.

---

## Critical (ships as slop)

### The purple-gradient hero

A hero/panel with a background gradient from purple to blue or purple to pink, often with white centred text. The single most-recognised AI aesthetic.

**Fix.** Pick a single anchor hue. One accent. No gradient backgrounds on heroes. If you want warmth, tint the neutrals.

### Inter-everywhere

Inter (or Roboto, or Open Sans) used as both display and body, with no pairing face.

**Fix.** Pair a distinctive display face with a refined body face.

### The 3-column feature grid

Three equal columns, each with an icon above a two-line heading above a three-line body.

**Fix.** Break the grid. Vary column widths. Mix card heights. Move icons inline, not above. Or drop cards and use typographic rhythm.

### Card-in-card

A bordered container with cards inside it, or a card containing another card. Visual nesting with no semantic reason.

**Fix.** Pick one containment layer. Usually the outer one is the wrong one.

### The gradient headline

A headline with `background-clip: text` fill set to a linear gradient.

**Fix.** Solid ink. Use weight, italic, or a display face to add life — not a gradient fill.

### The side-stripe card

A card with a thick coloured border on one edge (usually left, 4–6px).

**Fix.** Use a hairline border all around, or no border, or a small accent square beside the heading.

### Full-viewport centred hero/panel

`min-height: 100vh`, everything centred, one short sentence, one big CTA.

**Fix.** Let the panel be the height of its content. Bias left or right.

### Pure black, pure white

`#000000` background or `#ffffff` surface used flat with no tinting.

**Fix.** Tint toward the app's anchor hue.

### The AI nav

Wordmark hard-left, 4–5 inline text links centred or right-grouped, a CTA button hard-right, full viewport width, sticky, white background, 1px hairline border-bottom — applied indiscriminately regardless of the page's actual function.

**Why it fails.** The shape is context-blind. When the nav can't tell you what kind of page you're on, it's templated, not designed.

**Fix.** Match the nav shape to the page's actual function and department. State the rationale.

### The AI footer

4 columns of links, social-icon row, copyright line, faint top-border, neutral grey — standard SaaS footer with no relevance to an internal tool's real needs.

**Fix.** Match footer content to what the page actually needs to close with, not a generic sitemap.

### Aurora-blob background

Flowing organic mesh blobs in purple-to-pink-to-cyan behind panel text.

**Fix.** Solid surface, or a subtle two-stop gradient + grain at low opacity.

### Floating-orb decoration

Ambient generic 3D spheres or blurred coloured circles with no semantic role.

**Fix.** Cut them.

### Sound-on autoplay

A hero video that auto-plays with audio, or lacks `muted`.

**Fix.** `<video autoplay muted loop playsinline>` — always all four.

### Lazy-loaded LCP

`loading="lazy"` on the largest-contentful-paint element (hero image/video).

**Fix.** `fetchpriority="high"` and `preload="metadata"` on the LCP element; lazy-load only below-the-fold media.

---

## Major (looks AI-generated / drifted)

### Bounce and elastic easing

Buttons that bounce in, icons that wobble on hover.

**Fix.** Exponential ease-out.

### Centred everything

Headline centred, body centred, button centred, section after section of centred columns.

**Fix.** Bias the layout. Breaking symmetry once is enough.

### Italic headers

A roman headline with one word flipped to italic, or an all-italic display face on every heading.

**Fix.** Headers are roman. Carry emphasis with weight, accent colour, or a drawn underline. Italic only in body-copy emphasis.

### Eyebrow on every section

Every section starts with an uppercase mono-cap eyebrow (`01 / EXAMPLES`) above or beside its heading, with no genuine ordinal meaning.

**Fix.** Zero eyebrows unless content is genuinely ordinal, capped at 1–2 per page. When used, heading goes directly underneath in the same column — never a two-column tag-left/header-right layout.

### Shadow-glow on dark

A card on a dark background with a `box-shadow` leaving a soft coloured halo.

**Fix.** On dark surfaces, use elevation via lightness, not shadow.

### Icon-tile feature card

Rounded rectangle, icon in a coloured square top-left, heading below, two lines of copy, "Learn more →" — the universal template.

**Fix.** Vary sizes/alignments, pull icon inline with heading, or drop the icon.

### Glassmorphism without purpose

Frosted-glass panels everywhere, usually over a gradient.

**Fix.** Only when it communicates real depth (overlay over content), never as pure decoration.

### Hover-only affordances

Hover reveals a menu/delete button/tooltip with crucial information; touch/keyboard users get nothing.

**Fix.** Every hover affordance needs a focus state and works via tap/click.

### Tabular data without tabular-nums

Prices, dates, or metrics that don't align vertically because of proportional figures.

**Fix.** `font-variant-numeric: tabular-nums` on any numeric-column container.

### Animate-on-scroll on everything

Every section fades in on scroll; the page never settles.

**Fix.** Pick one orchestrated entrance. Let the rest just be there.

### Mismatched icon sets

Material Icons in the navbar, Heroicons in cards, Lucide in the footer, an emoji in a badge.

**Fix.** Pick one icon library per project.

### AI-illustration look

Smooth-mesh-blob characters, mid-2010s "modern flat" stock poses, corporate-doodle humans.

**Fix.** Hand-build in CSS/SVG, or use real screenshots/photography.

### Invented metrics

A stat-led layout or proof bar carrying numbers never supplied by a real source — the dashboard live+mock-data-mixing failure mode already found in this app falls under this.

**Fix.** Replace with `—` + labelled placeholder, ask for the real number, or rebuild the section without the proof slot.

### Generic emoji as feature icon

A feature card, status, or step rendered with `✨` `🚀` `⚡` `🔥` `🎯` `✅` as the primary icon.

**Fix.** Pick a real icon library, build a custom SVG, or omit the icon and lead with typography.

### Re-drawn UI chrome

A fake browser bar, fake phone frame, fake code-block window, or fake IDE chrome hand-built in HTML/CSS/SVG.

**Fix.** Use a real screenshot wrapped in `<figure>`, or omit the chrome.

### Mid-render token improvisation

A theme/token set is defined, but the file also contains inline colour values or font-family declarations that bypass it.

**Fix.** Every colour/font references a named token; add missing values to the token block first.

### Wrap-to-two-lines clickable text

A button label, nav link, or CTA reads on two lines at some viewport width.

**Fix.** Shorten the label, `white-space: nowrap` + reflow, or collapse into a menu at narrow widths.

### Lottie shortcut

A LottieFiles community animation (spinner, checkmark draw, loading dots) where CSS/SVG would work as well or better.

**Fix.** Build it custom in CSS/SVG.

### Three.js for a still, non-interactive object

A WebGL element that's just a stationary spinning model the user can't touch or reorient.

**Fix.** Use a static photograph or hand-built SVG instead.

---

## Microinteraction tells

### `transition-all`

Every property animating, including ones that should be instant (visibility, focus rings).

**Fix.** Specify the properties explicitly.

### Universal `hover:scale-105`

Every card lifts on hover with no other signal.

**Fix.** Pick one signal per element.

### Bouncy overshoot easings on UI

`cubic-bezier(0.34, 1.56, 0.64, 1)` and friends on buttons/modals/tooltips.

**Fix.** Reserve overshoots for genuine physical interactions (drag release). Use a standard ease-out for UI state.

### Animated hover gradients

Background gradient slides through colour space on hover.

**Fix.** Cut, or pick one instant colour shift.

### Cursor follower dots

A trailing dot lagging behind the pointer.

**Fix.** Cut.

### Auto-rotating carousels with no pause

WCAG 2.2.2 failure.

**Fix.** Manual advance, or pause-on-hover-and-focus.

### Celebratory success toasts

"Done!" for an action whose effect the user can already see.

**Fix.** Silent success. Toasts for failures and invisible-effect async actions only.

### Confirmation dialogs for reversible actions

A modal "Are you sure?" before a one-row delete.

**Fix.** Optimistic action + Undo toast. Reserve modals for irreversible actions.

### Tooltips with equal hover/focus delay

Both delay 800ms.

**Fix.** Hover delay 800–1000ms; focus delay 0ms.

### Focus rings that animate in

The ring fades in over time instead of appearing instantly.

**Fix.** Focus rings appear instantly, no transition.

### Toasts that shift layout

A new toast pushes content down.

**Fix.** Fixed-position stack at a viewport corner.

### Spinners that flash

A spinner appears for 50ms while a fast action completes.

**Fix.** Delay-show (150ms) or enforce a minimum visible duration (300ms). Prefer skeletons when layout is known.

---

## Minor (small taste issues)

### Straight quotes / double-hyphen dashes / three-dot ellipsis

`"Hello"`, `--`, `...` in rendered copy instead of curly quotes, em-dash, ellipsis character.

### Placeholder names

"Jane Doe", "Example User" instead of plausible, audience-appropriate names.

### Startup-cliché naming

"Acme", "Nexus", "Pulse", "Unleash" instead of concrete, domain-specific names.

### `z-index: 9999`

Arbitrary large z-values instead of a named scale.

### Every section padded the same

No variation in top/bottom/horizontal padding across sections.

### `100vw` widths

Breaks on scrollbar-visible desktops; use `100%` with container padding.

---

## Report format

For each finding:

```
[severity] Tell name — file:line
  why it's a tell (one line)
  → fix (one line)
```

Then:

```
Summary — N critical · M major · K minor
Verdict — [ships as slop | reads as AI-generated | close, fix the minors | clean]
```
