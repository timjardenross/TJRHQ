import { redirect } from 'next/navigation';
import { createSupabaseServerClient } from '@/lib/supabase-server';

// Root page: authenticate, then redirect to the workbench directory.
//
// 2026-08 UX review: /workbenches is the one canonical landing page — it
// lists every real workbench as a direct tile, and /workbenches itself has
// carried this exact "root redirect goes here" comment since it was built.
// This file previously redirected to /home (a since-retired "needs
// attention" triage feed) while claiming /workbenches was merely "an
// alternative directory" — the two pages disagreed with each other about
// which was authoritative. This was the stale one; /home is now a retired
// stub (see home/page.tsx) pointing back here, same pattern as /decisions.
export default async function RootPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();

  redirect(user ? '/workbenches' : '/login');
}
