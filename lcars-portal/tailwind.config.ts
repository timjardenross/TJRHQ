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
  ],
  theme: {
    extend: {
      colors: {
        // ── Department colours (mission spec) ──────────────────────────
        command: { DEFAULT: '#FFB81C', soft: '#FFD700' }, // Command Gold
        engineering: { DEFAULT: '#FF9800', soft: '#FFA726' }, // Engineering Orange
        operations: { DEFAULT: '#F44336', soft: '#FF6E63' }, // Operations Red
        medical: { DEFAULT: '#0099FF', soft: '#4FC3F7' }, // Medical Blue
        science: { DEFAULT: '#CC88FF', soft: '#D9A6FF' }, // Science Purple
        status: { DEFAULT: '#4CAF50', soft: '#81C784' }, // Status Green

        // ── LCARS chrome / backgrounds — LCARS light palette ──────────
        space: '#dce8f4',      // light blue-grey (body)
        panel: '#eaf1f8',      // lighter panel / card surface
        'panel-2': '#ccd8ec',  // slightly deeper panel variant
        edge: '#8aadc4',       // border / separator
        lcars: {
          amber: '#FF9966',
          peach: '#FFCC99',
          lilac: '#9999FF',
          ice: '#99CCFF',
          text: '#0d1f33',     // dark navy text
          muted: '#4a6b88'     // blue-grey muted text
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
