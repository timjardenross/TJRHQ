import { redirect } from 'next/navigation';
import { createSupabaseServerClient } from '@/lib/supabase-server';

// Root page: authenticate, then redirect to home dashboard.
//
// After login, users land on /home — a unified dashboard showing what needs
// attention across all surfaces (hot signals, pending QA, Captain's Brief
// interrupts, source health). A quiet day renders as "All Clear" rather than
// a wall of empty cards. Deep links to individual workbenches are available
// from the home dashboard and sidebar navigation. /workbenches still exists
// as an alternative workbench directory.
export default async function RootPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();

  redirect(user ? '/home' : '/login');
}
