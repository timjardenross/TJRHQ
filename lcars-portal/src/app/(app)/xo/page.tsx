'use client';

// Retired — duplicated Advisory Council's XO tab (same role, same
// underlying endpoint — advisory-council's COUNCIL entry for 'xo' has
// useXoEndpoint: true). MSN-0328 (WP-B): Advisory Council is the real,
// kept destination; select XO from its advisor roster.
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function XoChatPage() {
  const router = useRouter();
  useEffect(() => { router.replace('/advisory-council'); }, [router]);
  return null;
}
