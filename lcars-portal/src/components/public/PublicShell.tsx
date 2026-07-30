import Link from 'next/link';
import type { ReactNode } from 'react';
import { StructuredData } from '@/components/public/StructuredData';
import { buildPublicSchemaSet } from '@/lib/public-schema';
import {
  CONTACT_RESPONSE_TIME,
  FOOTER_PUBLIC_NAV,
  PRIMARY_PUBLIC_NAV,
  PUBLIC_SITE_NAME,
  SUPPORT_EMAIL,
  buildBreadcrumbs,
} from '@/lib/public-site';

export function PublicShell({
  path,
  eyebrow,
  title,
  intro,
  children,
}: {
  path: string;
  eyebrow: string;
  title: string;
  intro: string;
  children: ReactNode;
}) {
  const breadcrumbs = buildBreadcrumbs(path);
  const schemas = buildPublicSchemaSet(path);

  return (
    <main className="min-h-screen bg-[#f5f7fb] text-[#172033]">
      <StructuredData data={schemas} />
      <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-5 py-6 sm:px-8 lg:px-10">
        <header className="mb-10 rounded-[32px] border border-[#d9e1f0] bg-white/92 px-5 py-5 shadow-[0_20px_60px_rgba(23,32,51,0.08)] sm:px-7">
          <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
            <div className="max-w-2xl">
              {path !== '/' && (
                <nav aria-label="Breadcrumb" className="mb-4">
                  <ol className="flex flex-wrap items-center gap-2 text-sm text-[#61718c]">
                    {breadcrumbs.map((crumb, index) => (
                      <li key={crumb.path} className="flex items-center gap-2">
                        {index > 0 && <span aria-hidden>/</span>}
                        {index === breadcrumbs.length - 1 ? (
                          <span aria-current="page">{crumb.name}</span>
                        ) : (
                          <Link href={crumb.path} className="hover:text-[#243b7a]">
                            {crumb.name}
                          </Link>
                        )}
                      </li>
                    ))}
                  </ol>
                </nav>
              )}
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-[#52627f]">
                {eyebrow}
              </p>
              <h1 className="text-3xl font-semibold normal-case tracking-[-0.03em] text-[#18223a] sm:text-4xl">
                {title}
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-[#4d5d77] sm:text-lg">
                {intro}
              </p>
            </div>

            <nav aria-label="Public" className="flex flex-wrap gap-2">
              {PRIMARY_PUBLIC_NAV.map((link) => (
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

        <footer className="mt-10 border-t border-[#d9e1f0] pt-6 text-sm text-[#5a6780]">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="max-w-2xl">
              <p className="font-medium text-[#24304b]">{PUBLIC_SITE_NAME}</p>
              <p className="mt-1">
                Practical resilience support, coaching, and education. {CONTACT_RESPONSE_TIME}
              </p>
              <p className="mt-1">
                Contact:{' '}
                <a href={`mailto:${SUPPORT_EMAIL}`} className="hover:text-[#243b7a]">
                  {SUPPORT_EMAIL}
                </a>
              </p>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {FOOTER_PUBLIC_NAV.map((link) => (
                <Link key={link.href} href={link.href} className="hover:text-[#243b7a]">
                  {link.label}
                </Link>
              ))}
              <Link href="/login" className="hover:text-[#243b7a]">
                Login
              </Link>
            </div>
          </div>
          <div className="pb-2 pt-4 text-sm text-[#6d7890]">
            Copyright © {new Date().getFullYear()} {PUBLIC_SITE_NAME}. All rights reserved.
          </div>
          <div className="sr-only">
            This website provides coaching and educational information and is not medical advice.
          </div>
        </footer>
      </div>
    </main>
  );
}
