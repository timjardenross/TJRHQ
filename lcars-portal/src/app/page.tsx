import { redirect } from 'next/navigation';
import { createSupabaseServerClient } from '@/lib/supabase-server';

// Root page: authenticate, then redirect to the front door.
//
// 2026-09-05: front door moved from /workbenches to /hub (LifeOS Hub — the
// trimmed, always-on-glance-display page; see hub/page.tsx's own header
// comment for the full design rationale). /workbenches — the full
// workbench directory — is still one tap away via the WorkbenchShell
// logo, matching the "workbenches behind it" architecture; it's no longer
// the landing page itself.
//
// 2026-08 UX review (superseded by the above, kept for history): this file
// previously redirected to /home (a since-retired "needs attention" triage
// feed) while claiming /workbenches was merely "an alternative directory"
// — the two pages disagreed about which was authoritative. /home is now a
// retired stub (see home/page.tsx).
export default async function RootPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();

  redirect(user ? '/hub' : '/login');
}
