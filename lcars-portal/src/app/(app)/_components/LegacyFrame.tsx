'use client';

import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { WorkbenchShell } from '@/components/ui/WorkbenchShell';

// Pages that already render their own WorkbenchShell; wrapping them again would nest two
// shells (two sidebars, two headers).
const OWN_SHELL = new Set(['/medical', '/decisions']);

export function LegacyFrame({ children }: { children: ReactNode }) {
  const pathname = (usePathname() ?? '').replace(/\/$/, '');
  if (OWN_SHELL.has(pathname)) return <>{children}</>;
  return (
    <WorkbenchShell
      title="TJR HQ"
      eyebrow="Compatibility route"
      tagline="TJR HQ · retained for bookmarks — use the linked workbench for current workflows"
      mode="command"
      wide
    >
      <aside
        data-route-family="legacy-compatibility"
        className="mb-4 rounded-md border border-wb-line bg-wb-surface px-3 py-2 text-wb-label text-wb-ink2"
        role="note"
      >
        Compatibility route: this older command-centre surface is retained for bookmarks only. Use the linked workbench destination for current workflows.
      </aside>
      {children}
    </WorkbenchShell>
  );
}
