import { redirect } from 'next/navigation';
import { createSupabaseServerClient } from '@/lib/supabase-server';

// usstjros' root previously rendered the embedded PublicShell marketing
// page (a pre-ADR-023 duplicate of the now-canonical public-site/
// tjrmindbody.com deployment). That confused the app's own front door
// with the public marketing site. This route now sends visitors straight
// into the Executive OS instead; the PublicShell pages remain reachable
// at their own paths pending the full ADR-023 removal.
export default async function RootPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();

  redirect(user ? '/home' : '/login');
}
