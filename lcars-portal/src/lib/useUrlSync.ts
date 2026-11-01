'use client';

import { useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

// USS-TJR-MSN-0395 Stream A: Next.js App Router's useSearchParams() updates
// asynchronously after router.replace() -- it is not a synchronous state
// setter. Two state-changing calls fired close together (before the first
// replace()'s navigation has re-rendered the component with fresh params)
// each build their next URL from the *same* stale params snapshot, and the
// second call's router.replace() silently overwrites the first's change.
//
// Fix: track the URL this hook itself last wrote in a ref, updated
// synchronously inside writeParams (not via a useEffect keyed on the hook's
// params -- that would still lag a rapid second call by one render). Every
// subsequent writeParams call builds from that ref, so it is always current
// regardless of whether React has re-rendered with the navigation yet.
export function useUrlSync(basePath: string) {
  const router = useRouter();
  const params = useSearchParams();
  // Seeded once from the hook's own params on mount; every write after
  // that updates the ref directly (see writeParams) rather than resyncing
  // from `params`, which is exactly the async value this hook works around.
  const paramsRef = useRef<URLSearchParams>(params);

  const writeParams = (mutate: (sp: URLSearchParams) => void) => {
    const sp = new URLSearchParams(Array.from(paramsRef.current.entries()));
    mutate(sp);
    paramsRef.current = sp;
    router.replace(`${basePath}?${sp.toString()}`, { scroll: false });
  };

  return { writeParams };
}
