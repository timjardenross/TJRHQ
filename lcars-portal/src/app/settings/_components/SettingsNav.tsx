'use client';

// Desktop-only left rail (mission §22: "a small left-side Settings
// navigation with the selected section on the right"). Mobile gets the
// vertical list at /settings instead (§23) — this component is hidden
// below lg entirely, not squeezed into a second nav.
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { SETTINGS_SECTIONS } from '@/lib/settings-sections';

export function SettingsNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Settings sections"
      className="hidden shrink-0 flex-col gap-1 lg:flex lg:w-56"
    >
      {SETTINGS_SECTIONS.map((section) => {
        const active = pathname === section.href;
        const Icon = section.icon;
        return (
          <Link
            key={section.slug}
            href={section.href}
            aria-current={active ? 'page' : undefined}
            className={[
              'flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] transition-colors',
              active
                ? 'bg-wb-sage-deep/10 font-medium text-wb-sage-deep'
                : 'text-wb-ink2 hover:bg-wb-surface-raised hover:text-wb-ink',
              'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep',
            ].join(' ')}
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden />
            {section.title}
          </Link>
        );
      })}
    </nav>
  );
}
