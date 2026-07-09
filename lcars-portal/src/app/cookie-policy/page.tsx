import type { Metadata } from 'next';
import { PublicShell } from '@/components/public/PublicShell';
import { buildPublicMetadata } from '@/lib/public-site';

export const metadata: Metadata = buildPublicMetadata('/cookie-policy');

const cookieSections = [
  {
    title: 'Why this policy exists',
    body: `This Cookie Policy explains how TJR Mind & Body uses cookies and similar technologies on the website. It is intended to help visitors understand what is used, why it is used, and what choices are available.`,
  },
  {
    title: 'Essential cookies',
    body: `The website may use essential cookies required for secure authentication, session handling, and access to the private LCARS portal. These are used for core functionality rather than advertising.`,
  },
  {
    title: 'Analytics and advertising',
    body: `At the time of writing, the public TJR Mind & Body website does not use third-party advertising cookies and is not set up for behavioural ad targeting. If analytics or additional tracking tools are introduced later, this policy should be updated accordingly.`,
  },
  {
    title: 'Similar technologies',
    body: `Some site functionality may also rely on browser storage or similar technologies for preferences, notification settings, or operational behaviour in the private portal experience.`,
  },
  {
    title: 'Managing cookies',
    body: `Most browsers allow you to review, block, or delete cookies through browser settings. Disabling essential cookies may affect secure login or parts of the private application experience.`,
  },
];

export default function CookiePolicyPage() {
  return (
    <PublicShell
      path="/cookie-policy"
      eyebrow="Cookie Policy"
      title="Cookie Policy"
      intro="This page explains the limited role cookies and similar technologies play on the TJR Mind & Body website."
    >
      <section className="rounded-[32px] border border-[#d9e1f0] bg-white p-6 shadow-[0_20px_60px_rgba(23,32,51,0.08)] sm:p-8">
        <div className="space-y-8">
          {cookieSections.map((section) => (
            <section key={section.title}>
              <h2 className="text-2xl font-semibold normal-case tracking-[-0.02em] text-[#1d2840]">
                {section.title}
              </h2>
              <p className="mt-3 text-base leading-8 text-[#31415f]">{section.body}</p>
            </section>
          ))}
        </div>
      </section>

      <aside className="space-y-6">
        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#eaf0fb] p-6">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#566889]">
            Current position
          </p>
          <p className="mt-4 text-sm leading-7 text-[#4b5c78]">
            Cookies are currently associated with security and private-portal functionality rather than public marketing analytics.
          </p>
        </section>

        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#1f2f5f] p-6 text-white">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#d9e4ff]">
            Browser controls
          </p>
          <p className="mt-4 text-sm leading-7 text-[#eef3ff]">
            You can usually manage cookie behaviour through your browser settings, but blocking essential cookies may affect secure login or related functionality.
          </p>
        </section>
      </aside>
    </PublicShell>
  );
}
