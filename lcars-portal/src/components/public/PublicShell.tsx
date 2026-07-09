import Link from 'next/link';
import type { ReactNode } from 'react';

const navLinks = [
  { href: '/', label: 'Home' },
  { href: '/founder-story', label: 'Founder Story' },
  { href: '/contact', label: 'Contact' },
  { href: '/login', label: 'Login' },
];

export function PublicShell({
  eyebrow,
  title,
  intro,
  children,
}: {
  eyebrow: string;
  title: string;
  intro: string;
  children: ReactNode;
}) {
  return (
    <main className="min-h-screen bg-[#f5f7fb] text-[#172033]">
      <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-5 py-6 sm:px-8 lg:px-10">
        <header className="mb-10 rounded-[32px] border border-[#d9e1f0] bg-white/92 px-5 py-5 shadow-[0_20px_60px_rgba(23,32,51,0.08)] sm:px-7">
          <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
            <div className="max-w-2xl">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-[#52627f]">
                {eyebrow}
              </p>
              <h1 className="text-3xl font-semibold tracking-[-0.03em] text-[#18223a] sm:text-4xl">
                {title}
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-[#4d5d77] sm:text-lg">
                {intro}
              </p>
            </div>

            <nav aria-label="Public" className="flex flex-wrap gap-2">
              {navLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="rounded-full border border-[#d3dbeb] px-4 py-2 text-sm font-medium text-[#24304b] transition hover:border-[#243b7a] hover:text-[#243b7a]"
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>

        <div className="grid flex-1 gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(280px,0.8fr)]">
          {children}
        </div>

        <footer className="mt-10 flex flex-col gap-3 border-t border-[#d9e1f0] pt-6 text-sm text-[#5a6780] sm:flex-row sm:items-center sm:justify-between">
          <p>TJR Mind &amp; Body offers support, coaching, education, and practical resilience tools.</p>
          <div className="flex gap-4">
            <Link href="/contact" className="hover:text-[#243b7a]">
              Contact
            </Link>
            <Link href="/login" className="hover:text-[#243b7a]">
              Private Login
            </Link>
          </div>
        </footer>
      </div>
    </main>
  );
}
