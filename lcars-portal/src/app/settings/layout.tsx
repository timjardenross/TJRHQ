import type { ReactNode } from 'react';
import { WorkbenchShell } from '@/components/ui/WorkbenchShell';
import { SettingsNav } from './_components/SettingsNav';

// TJR HQ Settings Page Redesign mission §22: one WorkbenchShell for the
// whole /settings subtree (not one per section page — that would double
// up the header/Sidebar/ThemeSelector chrome). Section pages render only
// their own heading + controls; this layout supplies the shared "SETTINGS
// / How HQ works for you" frame and the responsive nav split (desktop
// left rail via SettingsNav, mobile falls back to the list at
// /settings — SettingsNav hides itself below lg).
export default function SettingsLayout({ children }: { children: ReactNode }) {
  return (
    <WorkbenchShell
      title="Settings"
      eyebrow="How HQ works for you"
      tagline="TJR HQ · Settings — preferences and defaults, not a diagnostics console. For job health and sync failures, see Agent & Job Status."
      wide
    >
      <div className="flex flex-col gap-6 lg:flex-row">
        <SettingsNav />
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </WorkbenchShell>
  );
}
