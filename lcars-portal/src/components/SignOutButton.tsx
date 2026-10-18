'use client';

import { useRouter } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

export function SignOutButton({ className = '' }: { className?: string }) {
  const router = useRouter();

  async function handleSignOut() {
    const supabase = createSupabaseBrowserClient();
    await supabase.auth.signOut();
    router.push('/login');
    router.refresh();
  }

  return (
    <button
      onClick={handleSignOut}
      className={`rounded-md px-3 py-2 text-left text-[12px] uppercase tracking-[0.2em] text-wb-ink2 transition-colors hover:text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${className}`}
    >
      Sign out
    </button>
  );
}
