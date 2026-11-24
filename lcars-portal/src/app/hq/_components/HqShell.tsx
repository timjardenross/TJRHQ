'use client';

// The HQ application shell: its own top bar, five-destination navigation
// (sidebar on desktop, bottom bar on phones), global search, the contextual
// New action and a quiet System and settings entry. Independent of the
// existing WorkbenchShell: it imports nothing from it.
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { HqProvider, useHq } from '@/lib/hq/HqProvider';
import { DecisionsIcon, GearIcon, HomeIcon, IntelIcon, LibraryIcon, WorkIcon } from './Icons';
import { NewDialog } from './NewDialog';

const NAV = [
  { href: '/hq', label: 'Home', Icon: HomeIcon, match: (p: string) => p === '/hq' },
  { href: '/hq/intelligence', label: 'Intelligence', Icon: IntelIcon, match: (p: string) => p.startsWith('/hq/intelligence') },
  { href: '/hq/decisions', label: 'Decisions', Icon: DecisionsIcon, match: (p: string) => p.startsWith('/hq/decisions') },
  { href: '/hq/work', label: 'Work', Icon: WorkIcon, match: (p: string) => p.startsWith('/hq/work') },
  { href: '/hq/library', label: 'Library', Icon: LibraryIcon, match: (p: string) => p.startsWith('/hq/library') },
] as const;

function NavLinks({ pathname, count }: { pathname: string; count: number }) {
  return (
    <>
      {NAV.map(({ href, label, Icon, match }) => (
        <Link key={href} href={href} className="hq-nav" aria-current={match(pathname) ? 'page' : undefined}>
          <Icon />
          <span>{label}</span>
          {label === 'Decisions' && count > 0 && <span className="hq-count" aria-label={`${count} waiting`}>{count}</span>}
        </Link>
      ))}
    </>
  );
}

function Chrome({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '/hq';
  const router = useRouter();
  const { decisions, materialProblem, openNew, toasts, dismissToast, newOpen } = useHq();
  const mainRef = useRef<HTMLElement>(null);
  const first = useRef(true);
  const [q, setQ] = useState('');

  // Move focus to the page content after client-side navigation so keyboard
  // and screen-reader users land on the new page, not on the nav they used.
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    mainRef.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }, [pathname]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    const term = q.trim();
    router.push(term ? `/hq/library?q=${encodeURIComponent(term)}` : '/hq/library');
  }

  return (
    <div className="hq">
      <a href="#hq-main" className="hq-skip">Skip to content</a>
      <header className="hq-top">
        <Link href="/hq" className="hq-brand" aria-label="HQ home">HQ</Link>
        <form onSubmit={onSearch} role="search" style={{ flex: 1, minWidth: 0, display: 'flex' }}>
          <input
            className="hq-search"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search everything"
            aria-label="Search everything you have saved"
            autoComplete="off"
          />
        </form>
        <button type="button" className="hq-btn primary" onClick={() => openNew()} aria-haspopup="dialog" aria-expanded={newOpen}>
          <span aria-hidden="true">+</span>
          <span className="lbl">New</span>
          <span style={{ position: 'absolute', left: -9999 }}>New: capture, research, ask, or mission</span>
        </button>
        <Link
          href="/hq/system"
          className="hq-btn quiet"
          aria-label={materialProblem ? 'System and settings, a problem needs attention' : 'System and settings'}
          aria-current={pathname.startsWith('/hq/system') ? 'page' : undefined}
        >
          <GearIcon />
          {materialProblem && <span className="hq-dot" aria-hidden="true" />}
        </Link>
      </header>
      <div className="hq-body">
        <nav className="hq-side" aria-label="HQ primary"><NavLinks pathname={pathname} count={decisions.length} /></nav>
        <main id="hq-main" className="hq-main" tabIndex={-1} ref={mainRef}>{children}</main>
      </div>
      <nav className="hq-bottom" aria-label="HQ primary (mobile)"><NavLinks pathname={pathname} count={decisions.length} /></nav>
      <div className="hq-toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="hq-toast">
            <span>{t.message}</span>
            {t.undo && <button type="button" onClick={async () => { await t.undo?.(); dismissToast(t.id); }}>Undo</button>}
          </div>
        ))}
      </div>
      <NewDialog />
    </div>
  );
}

export function HqShell({ children }: { children: ReactNode }) {
  return (
    <HqProvider>
      <Chrome>{children}</Chrome>
    </HqProvider>
  );
}
