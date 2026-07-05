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
  ],
  theme: {
    extend: {
      colors: {
        // ── Department colours (mission spec) ──────────────────────────
        // DEFAULT/soft: vivid, for bg fills (bars, icons, pills)
        // on: darker shade, readable as text on the light #dce8f4 background
        command:     { DEFAULT: '#FFB81C', soft: '#FFD700', on: '#7A4D00' }, // Command Gold
        engineering: { DEFAULT: '#FF9800', soft: '#FFA726', on: '#8A3C00' }, // Engineering Orange
        operations:  { DEFAULT: '#F44336', soft: '#FF6E63', on: '#B71C1C' }, // Operations Red
        medical:     { DEFAULT: '#0099FF', soft: '#4FC3F7', on: '#005299' }, // Medical Blue
        science:     { DEFAULT: '#CC88FF', soft: '#D9A6FF', on: '#5B2AAA' }, // Science Purple
        status:      { DEFAULT: '#4CAF50', soft: '#81C784', on: '#1B5E20' }, // Status Green (legacy — see `state` below)

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
      },
      borderRadius: {
        lcars: '1.25rem'
      }
    }
  },
  plugins: [require('@tailwindcss/typography')]
};

export default config;
