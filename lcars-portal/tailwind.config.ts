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
  ],
  theme: {
    extend: {
      colors: {
        // ── Phase B Intelligence Workbench — warm brand palette ────────
        // TJR Mind & Body direction (Phase-B design sign-off, D6). `ink`/`ink2`
        // on `bg`/`surface` pass WCAG AA as text; `sage` is an accent for
        // fills/borders/large-text only (fails AA as small text), `sage-deep`
        // is the text-safe variant. Validate any new pairing with the method in
        // docs/design-tokens/PHASE-1A-CONTRAST-MATRIX.md.
        wb: {
          bg:       '#FAF8F3',
          surface:  '#FFFFFF',
          line:     '#E8E5DC',
          ink:      '#2D2D2D',
          ink2:     '#5A5A5A',
          sage:     '#8B9E8B',
          'sage-deep': '#52604F',
          ok:       '#6B8E6B',
          warn:     '#B57A34',
          crit:     '#C85A54',
          // AA-safe (>=4.5:1) text/solid-button variants of the status hues.
          // sage/ok/warn/crit fail AA as small text or white-on-fill; use these
          // for pill text and white-on-colour buttons. Contrast validated
          // (docs/design-tokens/PHASE-1A-CONTRAST-MATRIX.md method).
          'ok-on':   '#3F633F',
          'warn-on': '#8A5A1B',
          'crit-on': '#A23A34',
          // Gradient endpoint for the escalation "critical incident" banner
          // (white text on top — high contrast preserved at both ends).
          // Promoted from a hardcoded bg-[#8a2f2a] arbitrary value.
          'crit-deep': '#8a2f2a',
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
          muted: '#3a5a78'     // strengthened blue-grey muted
        }
      },
      fontFamily: {
        sans:  ['"Inter"', '"Helvetica Neue"', 'Arial', 'sans-serif'],
        lcars: ['"Inter"', '"Helvetica Neue"', 'Arial', 'sans-serif'],
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
