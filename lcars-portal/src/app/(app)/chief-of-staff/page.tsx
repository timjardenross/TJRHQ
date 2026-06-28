'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function ChiefOfStaffRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace('/advisory-council'); }, [router]);
  return null;
}
