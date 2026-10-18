'use client';

import Link from 'next/link';
import { WorkbenchShell } from './WorkbenchShell';

// A page that has been decommissioned from HQ. Keeps the URL answering (bookmarks) with an
// honest notice and a link to where the content now lives, inside the normal shell.
export function RetiredPageNotice({
  title,
  message,
  links,
}: {
  title: string;
  message: string;
  links: { href: string; label: string }[];
}) {
  return (
    <WorkbenchShell title={title} eyebrow="Retired from HQ" tagline="TJR HQ" mode="command" quiet>
      <div className="mx-auto max-w-2xl py-8">
        <p className="text-wb-body leading-relaxed text-wb-ink2">{message}</p>
        <ul className="mt-4 space-y-2 text-wb-body">
          {links.map((l) => (
            <li key={l.href}>
              <Link href={l.href} className="text-wb-sage-deep underline hover:no-underline">
                {l.label} →
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </WorkbenchShell>
  );
}
