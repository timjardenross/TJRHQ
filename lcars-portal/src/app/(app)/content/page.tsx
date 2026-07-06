'use client';

// Retired — duplicated Communications, both reading/writing the same
// comms_content table via separate API routes (/api/content/pipeline vs
// /api/comms). MSN-0328 (WP-B): /comms is the real, kept destination.
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function ContentPage() {
  const router = useRouter();
  useEffect(() => { router.replace('/comms'); }, [router]);
  return null;
}
