import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import { SETTINGS_SECTIONS } from '@/lib/settings-sections';

// Mission §23: "Mobile should use a simple settings list." On desktop this
// is what shows in the right-hand pane before a section is picked from
// SettingsNav — a deliberate, well-known pattern (macOS System Settings,
// GitHub Settings both do the same) rather than guessing which section to
// auto-open. On mobile (where SettingsNav hides itself), this list IS the
// Settings page.
export default function SettingsIndexPage() {
  return (
    <nav aria-label="Settings sections" className="divide-y divide-wb-line rounded-lg border border-wb-line bg-wb-surface">
      {SETTINGS_SECTIONS.map((section) => {
        const Icon = section.icon;
        return (
          <Link
            key={section.slug}
            href={section.href}
            className="flex items-center gap-3 px-4 py-4 text-wb-ink transition-colors hover:bg-wb-surface-raised focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-wb-sage-deep"
          >
            <Icon className="h-4 w-4 shrink-0 text-wb-ink2" aria-hidden />
            <span className="min-w-0 flex-1">
              <span className="block text-[14px] font-medium">{section.title}</span>
              <span className="block text-[12px] text-wb-ink2">{section.description}</span>
            </span>
            <ChevronRight className="h-4 w-4 shrink-0 text-wb-ink2" aria-hidden />
          </Link>
        );
      })}
    </nav>
  );
}
