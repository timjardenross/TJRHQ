import Link from 'next/link';

export interface TabItem<T extends string = string> {
  key: T;
  label: string;
}

export interface TabsProps<T extends string = string> {
  tabs: TabItem<T>[];
  active: T;
  onChange: (key: T) => void;
  ariaLabel: string;
}

/** TJR Design System — generalized from comms-workbench's tab nav. */
export function Tabs<T extends string = string>({ tabs, active, onChange, ariaLabel }: TabsProps<T>) {
  return (
    <nav className="flex gap-2 border-b border-wb-line pb-2" aria-label={ariaLabel}>
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          onClick={() => onChange(t.key)}
          aria-current={active === t.key ? 'page' : undefined}
          className={`rounded border px-3 py-1.5 text-xs transition-colors focus-visible:outline
            focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${
              active === t.key
                ? 'border-wb-sage-deep bg-wb-sage-deep/10 text-wb-sage-deep'
                : 'border-wb-line text-wb-ink2 hover:text-wb-ink'
            }`}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}

export interface BackLinkProps {
  href: string;
  label: string;
}

/** TJR Design System — extracted from intelligence-workbench/_components/Shell.tsx `back` prop. */
export function BackLink({ href, label }: BackLinkProps) {
  return (
    <Link
      href={href}
      className="mb-4 inline-block text-[13px] text-wb-sage-deep hover:underline focus-visible:outline
        focus-visible:outline-2 focus-visible:outline-wb-sage-deep"
    >
      ← {label}
    </Link>
  );
}
