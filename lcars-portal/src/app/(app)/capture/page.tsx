// Capture was reskinned onto the wb- design system as the Capture Workbench
// (/capture-workbench). Per Captain decision 2026-07-12, this path stays alive
// during the validation soak as a query-preserving redirect, then is removed.
// The ?filter= deep-link contract (alerts/search) is carried through unchanged.
//
// See CAPTURE-WORKBENCH-MIGRATION-PLAN.md §9 (Phase D).

import { redirect } from 'next/navigation';

export const dynamic = 'force-dynamic';

export default function CaptureRedirect({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>;
}) {
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    const v = Array.isArray(value) ? value[0] : value;
    if (v !== undefined) sp.set(key, v);
  }
  const qs = sp.toString();
  redirect(`/capture-workbench${qs ? `?${qs}` : ''}`);
}
