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
    'bg-command',
    'bg-engineering',
    'bg-operations',
    'bg-medical',
    'bg-science',
    'bg-status',
    'bg-lcars-muted',
    'text-engineering',
    'border-engineering',
    'xl:grid-cols-5',
    'xl:flex'
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

        // ── LCARS chrome / backgrounds ─────────────────────────────────
        space: '#05070e',
        panel: '#12162e',
        'panel-2': '#1a1f3d',
        edge: '#2a2f52',
        lcars: {
          amber: '#FF9966',
          peach: '#FFCC99',
          lilac: '#9999FF',
          ice: '#99CCFF',
          text: '#D6E0FF',
          muted: '#8A93C2'
        }
      },
      fontFamily: {
        lcars: ['"Antonio"', '"Helvetica Neue"', 'Arial', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace']
      },
      borderRadius: {
        lcars: '1.25rem'
      }
    }
  },
  plugins: []
};

export default config;
