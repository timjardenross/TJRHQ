# Accessibility regression suite

The portal now has an explicit regression contract covering the four required
assistive-use conditions:

- Keyboard: native links/buttons, visible `:focus-visible`, and the first-tab
  skip link to `#wb-main`.
- Zoom/reflow: fluid shell primitives and no fixed-width main content; the
  mobile viewport sweep should be run at 200% equivalent zoom in a browser.
- Reduced motion: the global stylesheet disables transitions/animations under
  `prefers-reduced-motion: reduce`.
- Screen readers: status changes use `role="status"`/`aria-live`, evidence is
  exposed through an `aria-label`, and controls retain accessible names.
- High contrast: `forced-colors: active` preserves borders and focus outlines
  using system colours instead of relying on the authored palette.

Automated coverage lives in
`src/components/ui/__tests__/accessibility-regression.test.tsx` and the
existing axe component suite. Browser-level zoom and screen-reader speech
output remain manual checks because jsdom cannot emulate a real assistive
technology or browser zoom engine.
