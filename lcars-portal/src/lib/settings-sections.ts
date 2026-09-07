// TJR HQ Settings — the section list, shared between the left-rail nav
// (desktop), the mobile list (app/settings/page.tsx), and each section's
// route segment. One array so the two presentations of "which sections
// exist" can't drift (same reasoning as lib/workbenches.ts's
// LIVE_WORKBENCHES for the hub tile grid + workbench switcher).

import type { LucideIcon } from 'lucide-react';
import { Palette, Compass, BellRing, Plug, Radar, Sparkles, ShieldCheck } from 'lucide-react';

export interface SettingsSection {
  slug: string;
  href: string;
  title: string;
  /** One line: what this section answers, shown under the title on both
   * the mobile list and the section heading itself. */
  description: string;
  icon: LucideIcon;
}

export const SETTINGS_SECTIONS: SettingsSection[] = [
  {
    slug: 'appearance',
    href: '/settings/appearance',
    title: 'Appearance',
    description: 'How HQ looks.',
    icon: Palette,
  },
  {
    slug: 'hq-behaviour',
    href: '/settings/hq-behaviour',
    title: 'HQ Behaviour',
    description: 'What HQ normally puts in front of you.',
    icon: Compass,
  },
  {
    slug: 'follow-through',
    href: '/settings/follow-through',
    title: 'Follow-through & Notifications',
    description: 'How HQ reminds you.',
    icon: BellRing,
  },
  {
    slug: 'connections',
    href: '/settings/connections',
    title: 'Connections',
    description: 'What services HQ uses.',
    icon: Plug,
  },
  {
    slug: 'intelligence',
    href: '/settings/intelligence',
    title: 'Intelligence',
    description: 'What HQ should care about.',
    icon: Radar,
  },
  {
    slug: 'ai-automation',
    href: '/settings/ai-automation',
    title: 'AI & Automation',
    description: 'How AI may assist.',
    icon: Sparkles,
  },
  {
    slug: 'data-privacy',
    href: '/settings/data-privacy',
    title: 'Data & Privacy',
    description: 'How your HQ data is handled.',
    icon: ShieldCheck,
  },
];
