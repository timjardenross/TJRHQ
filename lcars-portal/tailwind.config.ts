import type { Config } from 'tailwindcss';

/**
 * LCARS / Starfleet palette.
 *
 * Department colours are the mission-mandated set. Hex values are aligned
 * with the existing Command Centre theme (theme-starfleet-advanced.css) so
 * the portal is visually consistent with Dashy and the legacy dashboards.
 */
const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  // Dot/accent classes that are composed at runtime (e.g. StatusBadge) — keep
  // them generated even though they don't appear verbatim in source.
  safelist: [
    // Department bg fills (StatusBadge dot, DepartmentRow icon, BottomNav)
    'bg-command',
    'bg-engineering',
    'bg-operations',
    'bg-medical',
    'bg-science',
    'bg-status',
    'bg-lcars-muted',
    'bg-lcars-lilac',
    // Department text / border (dynamic composition in departments.ts)
    'text-engineering',
    'border-engineering',
    // Dark-on-light readable text variants
    'text-command-on',
    'text-engineering-on',
    'text-operations-on',
    'text-medical-on',
    'text-science-on',
    'text-status-on',
    // Operational state classes (dynamic composition in departments.ts stateToneClasses — MSN-0315 Phase 1B)
    'bg-state-ok', 'bg-state-ok/15', 'text-state-ok', 'border-state-ok', 'text-state-ok-on',
    'bg-state-warn', 'bg-state-warn/15', 'text-state-warn', 'border-state-warn', 'text-state-warn-on',
    'bg-state-crit', 'bg-state-crit/15', 'text-state-crit', 'border-state-crit', 'text-state-crit-on',
    'bg-state-unknown', 'bg-state-unknown/15', 'text-state-unknown', 'border-state-unknown', 'text-state-unknown-on',
    'bg-state-info', 'bg-state-info/15', 'text-state-info', 'border-state-info', 'text-state-info-on',
  ],
  theme: {
    extend: {
      colors: {
        // ── Phase B Intelligence Workbench — warm brand palette ────────
        // 2026-08-09: re-pulled from the live TJR Mind & Body site
        // (tjrmindbody.com/about's actual compiled CSS, not guessed) —
        // this token set was always meant to match that brand ("TJR Mind
        // & Body direction", Phase-B design sign-off) but had drifted to a
        // generic sage-green palette that never matched the real site's
        // teal/navy/cream/gold system. `sage`/`sage-deep` keep their
        // existing names (hundreds of call sites) but now hold the site's
        // real teal values — bg-wb-sage-deep etc. re-theme automatically,
        // no call-site changes needed. `ink`/`ink2` on `bg`/`surface` pass
        // WCAG AA as text; `sage` is an accent for fills/borders/large-text
        // only (fails AA as small text — 4.05:1, same constraint the old
        // value had), `sage-deep` is the text-safe variant (7.85:1 on
        // white). `gold` is a decorative/border accent ONLY (2.1-2.3:1 —
        // fails AA badly as text at any size; the real site only ever uses
        // it for blockquote borders, never text). Validate any new pairing
        // with the method in docs/design-tokens/PHASE-1A-CONTRAST-MATRIX.md.
        // 2026-09-05 (Adaptive Themes mission): every value below now reads
        // a CSS custom property (defined per-theme in globals.css, keyed by
        // [data-theme] on <html>) instead of a literal hex — same class
        // names everywhere (bg-wb-bg, text-wb-ink2, ...), so no call site
        // anywhere in the app needed to change. `archive` theme's variable
        // values are what used to be hardcoded here directly; every other
        // theme just supplies different values for the same variables.
        wb: {
          bg:       'var(--wb-bg)',
          surface:  'var(--wb-surface)',
          'surface-raised': 'var(--wb-surface-raised)',
          line:     'var(--wb-line)',
          ink:      'var(--wb-ink)',
          ink2:     'var(--wb-ink2)',
          sage:     'var(--wb-sage)',
          'sage-deep': 'var(--wb-sage-deep)',
          navy:     'var(--wb-navy)',
          gold:     'var(--wb-gold)',
          ok:       'var(--wb-ok)',
          warn:     'var(--wb-warn)',
          crit:     'var(--wb-crit)',
          // AA-safe (>=4.5:1) text/solid-button variants of the status hues.
          // sage/ok/warn/crit fail AA as small text or white-on-fill; use these
          // for pill text and white-on-colour buttons. Contrast validated
          // (docs/design-tokens/PHASE-1A-CONTRAST-MATRIX.md method) — and,
          // as of the theme system, per-theme (see globals.css).
          'ok-on':   'var(--wb-ok-on)',
          'warn-on': 'var(--wb-warn-on)',
          'crit-on': 'var(--wb-crit-on)',
          // Gradient endpoint for the escalation "critical incident" banner
          // (white text on top — high contrast preserved at both ends).
          'crit-deep': 'var(--wb-crit-deep)',
        },
        // ── Department colours (mission spec) ──────────────────────────
        // DEFAULT/soft: vivid, for bg fills (bars, icons, pills)
        // on: darker shade, readable as text on the light #dce8f4 background
        command:     { DEFAULT: '#FFB81C', soft: '#FFD700', on: '#7A4D00' }, // Command Gold
        engineering: { DEFAULT: '#FF9800', soft: '#FFA726', on: '#8A3C00' }, // Engineering Orange
        operations:  { DEFAULT: '#F44336', soft: '#FF6E63', on: '#B71C1C' }, // Operations Red
        medical:     { DEFAULT: '#0099FF', soft: '#4FC3F7', on: '#005299' }, // Medical Blue
        science:     { DEFAULT: '#CC88FF', soft: '#D9A6FF', on: '#5B2AAA' }, // Science Purple
        status:      { DEFAULT: '#1B5E20', soft: '#81C784', on: '#1B5E20' }, // Status Green (legacy — see `state` below). DEFAULT re-shaded Phase 1F (was #4CAF50, failed both 3:1 UI-component and 4.5:1 text contrast — reused the already-validated `on` value since `text-status` is used directly as body text throughout the app, not just via `-on`)

        // ── Operational state colours (MSN-0315 Phase 1A) ──────────────
        // Independent of department identity colour — per the ratified rule
        // "operational status colours are sacred, never overridden by
        // department colour" (revived from archive/.../STARFLEET-DESIGN-STANDARD.md
        // §2, carried forward by MSN-0310 §4.2). Consumers (StatusBadge etc.)
        // are migrated onto these in Phase 1B — not touched here.
        // Values below are contrast-validated (>=3:1 DEFAULT, >=4.5:1 "on")
        // against all three live backgrounds; see
        // lcars-portal/docs/design-tokens/PHASE-1A-CONTRAST-MATRIX.md.
        state: {
          ok:      { DEFAULT: '#278A44', soft: '#cfe8d5', on: '#1B5E20' }, // Healthy / Operational
          warn:    { DEFAULT: '#9C5D10', soft: '#f0ddc4', on: '#7A4610' }, // Warning / Attention Required
          crit:    { DEFAULT: '#C43030', soft: '#f8dcdc', on: '#7A1616' }, // Critical / Action Required
          unknown: { DEFAULT: '#5A6690', soft: '#dfe2ee', on: '#33395C' }, // Unknown / No Data
          // Added 2026-08-29 (docs/Severity-Vocab-Canonicalization-Plan-
          // 2026-08-29.md), merging in Badge's independent 'info' status.
          // Reuses the exact hex values already shipped as wb-sage/
          // wb-sage-deep (Badge's current info tone) rather than inventing
          // a new hue, so this doesn't visually change anything already
          // rendering — just gives the value a canonical home. DEFAULT
          // computes to ~4.05:1 against white (passes the >=3:1 bar); on
          // computes to ~7.85:1 against white (passes the >=4.5:1 bar) —
          // computed here, not re-run through
          // docs/design-tokens/PHASE-1A-CONTRAST-MATRIX.md's actual
          // measurement method; re-verify there before treating as final.
          info:    { DEFAULT: '#2E8B8B', soft: '#d6ebeb', on: '#0F5B5D' }, // Informational / Benign
        },

        // ── LCARS chrome / backgrounds — LCARS light palette ──────────
        space: '#dce8f4',      // light blue-grey (body)
        panel: '#eaf1f8',      // lighter panel / card surface
        'panel-2': '#ccd8ec',  // slightly deeper panel variant
        edge: '#8aadc4',       // border / separator
        lcars: {
          amber: '#FF9966',
          peach: '#FFCC99',
          lilac: '#6644CC',    // darkened lilac — readable on light bg
          ice: '#1A6EA8',      // darkened ice — readable on light bg
          text: '#0d1f33',     // dark navy text
          muted: '#3a5a78',    // strengthened blue-grey muted
          // Chrome tokens for LCARSPanel + departments.ts toneClasses() —
          // promoted from inline hexes (design-audit finding, gate 48).
          'chrome-border': '#d9e1f0',
          'chrome-border-soft': '#eef1f8',
          'chrome-muted': '#61718c',
          'chrome-text': '#18223a',
          'chrome-accent': '#243b7a',
        }
      },
      fontFamily: {
        sans:  ['"Inter"', '"Helvetica Neue"', 'Arial', 'sans-serif'],
        mono:  ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        // TJR Design System — locked serif for wb.* headings (Card/Shell titles).
        // Loaded via next/font/google in src/app/layout.tsx as --font-serif.
        serif: ['var(--font-serif)', 'ui-serif', 'Georgia', 'serif'],
      },
      borderRadius: {
        lcars: '1.25rem'
      }
    }
  },
  plugins: [require('@tailwindcss/typography')]
};

export default config;
