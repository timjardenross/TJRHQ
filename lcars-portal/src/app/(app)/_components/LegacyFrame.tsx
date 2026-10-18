'use client';

import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { WorkbenchShell } from '@/components/ui/WorkbenchShell';

// Pages that already render their own WorkbenchShell; wrapping them again would nest two
// shells (two sidebars, two headers).
export const OWN_SHELL = new Set(['/decisions']);

export function LegacyFrame({ children }: { children: ReactNode }) {
  const pathname = (usePathname() ?? '').replace(/\/$/, '');
  if (OWN_SHELL.has(pathname)) return <>{children}</>;
  return (
    <WorkbenchShell
      title="TJR HQ"
      eyebrow="Older page"
      tagline="TJR HQ · retained for bookmarks — use the linked workbench for current workflows"
      mode="command"
      quiet
      wide
    >
      {children}
    </WorkbenchShell>
  );
}
