'use client';

import { useAlertCount } from '@/lib/useAlerts';

// Headless global owner of native push-notification firing for
// critical/high alerts (useAlertCount's `enableNotifications: true` — see
// useAlerts.ts). Split out of MobileCommandBar (2026-09-12 mobile-nav
// removal, WORKBENCH-MOBILE-COMPAT): removing that bar from every
// *-workbench route (it was fixed-position, full-width, z-50 — sitting
// directly on top of QuickCapture's floating "+" button and clipping the
// last ~90px of every page's content, both unnoticed on desktop where the
// bar is `xl:hidden`) must not also silently stop real notifications, since
// nothing else in the app calls useAlertCount(). Mount this wherever
// MobileCommandBar used to be mounted for that reason alone.
export function GlobalAlertNotifier() {
  useAlertCount();
  return null;
}
