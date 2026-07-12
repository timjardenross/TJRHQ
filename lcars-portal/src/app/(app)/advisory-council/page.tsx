// The Advisory Council was reskinned onto the wb- design system as the
// Advisory Workbench (/advisory-workbench). Per Captain decision 2026-07-12,
// this path stays alive during the validation soak as a query-preserving
// redirect, then is removed. Legacy ?tab= is mapped to the workbench's ?domain=.
//
// See ADVISORY-COUNCIL-WORKBENCH-MIGRATION-PLAN.md §9 (Phase E).

import { redirect } from 'next/navigation';

export const dynamic = 'force-dynamic';

export default function AdvisoryCouncilRedirect({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>;
}) {
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    const v = Array.isArray(value) ? value[0] : value;
    if (v === undefined) continue;
    // Legacy ?tab= is the workbench's ?domain=.
    sp.set(key === 'tab' ? 'domain' : key, v);
  }
  const qs = sp.toString();
  redirect(`/advisory-workbench${qs ? `?${qs}` : ''}`);
}
