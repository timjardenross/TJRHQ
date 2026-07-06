'use client';

// Retired — merged into Intelligence. Both read the same underlying
// tables (intelligence_briefs, intelligence_source_health — see
// /api/intelligence/route.ts). MSN-0328 (WP-B).
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function XoBriefPage() {
  const router = useRouter();
  useEffect(() => { router.replace('/intelligence'); }, [router]);
  return null;
}
