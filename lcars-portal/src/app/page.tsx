import { redirect } from 'next/navigation';
import { createSupabaseServerClient } from '@/lib/supabase-server';

// Root page: authenticate, then redirect to workbenches hub.
//
// After login, users land on /workbenches (the new home page per MSN-0350),
// a tile grid of all available workbenches and surfaces. This replaces the
// previous static HomeScreen approach, emphasizing choice and deliberate
// navigation.
export default async function RootPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();

  redirect(user ? '/workbenches' : '/login');
}
