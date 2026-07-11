import type { Metadata } from 'next';
import { PublicShell } from '@/components/public/PublicShell';
import { buildPublicMetadata } from '@/lib/public-site';

export const metadata: Metadata = buildPublicMetadata('/terms-conditions');

const terms = [
  {
    title: 'Website purpose',
    body: `This website is provided to share information about TJR Mind & Body, its coaching and educational approach, and ways to make contact. It is not a public clinical portal and it does not provide personalised medical, diagnostic, or emergency advice.`,
  },
  {
    title: 'Use of the website',
    body: `By using this website, you agree to use it lawfully, respectfully, and only for legitimate informational or enquiry-related purposes. You must not attempt to misuse, disrupt, reverse engineer, or gain unauthorised access to private areas of the site or related systems.`,
  },
  {
    title: 'Educational and coaching content',
    body: `Content on this website is intended for general educational and coaching-related information only. It should not be relied on as a substitute for professional medical, psychological, legal, or financial advice tailored to your circumstances.`,
  },
  {
    title: 'Intellectual property',
    body: `Unless otherwise stated, website content, structure, written material, branding, and original assets remain the property of TJR Mind & Body. You may view and share the site for personal, non-misleading purposes, but you must not reproduce or republish substantial content in a way that implies endorsement, ownership, or formal permission.`,
  },
  {
    title: 'Links to third-party content',
    body: `This website may link to third-party websites or resources for convenience. Those external sites are not controlled by TJR Mind & Body, and responsibility is not accepted for their content, availability, or privacy practices.`,
  },
  {
    title: 'No guarantee of outcomes',
    body: `TJR Mind & Body does not guarantee results, outcomes, or improvements from website content, conversations, or future coaching support. Progress depends on many personal, practical, and contextual factors.`,
  },
  {
    title: 'Liability limitation',
    body: `To the extent permitted by law, TJR Mind & Body is not liable for loss or damage arising from reliance on general website content, temporary website interruptions, or third-party services outside reasonable control.`,
  },
  {
    title: 'Changes to these terms',
    body: `These Terms & Conditions may be updated from time to time. Continued use of the website after changes are published indicates acceptance of the revised terms.`,
  },
];

export default function TermsConditionsPage() {
  return (
    <PublicShell
      path="/terms-conditions"
      eyebrow="Terms & Conditions"
      title="Terms & Conditions"
      intro="These terms govern use of the TJR Mind & Body website and help clarify the scope and limits of the public content provided here."
    >
      <section className="rounded-[32px] border border-[#d9e1f0] bg-white p-6 shadow-[0_20px_60px_rgba(23,32,51,0.08)] sm:p-8">
        <div className="space-y-8">
          {terms.map((term) => (
            <section key={term.title}>
              <h2 className="text-2xl font-semibold normal-case tracking-[-0.02em] text-[#1d2840]">
                {term.title}
              </h2>
              <p className="mt-3 text-base leading-8 text-[#31415f]">{term.body}</p>
            </section>
          ))}
        </div>
      </section>

      <aside className="space-y-6">
        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#eaf0fb] p-6">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#566889]">
            Scope reminder
          </p>
          <p className="mt-4 text-sm leading-7 text-[#4b5c78]">
            The public website is for information, trust-building, and initial contact. Private LCARS routes remain restricted to authorised users only.
          </p>
        </section>

        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#1f2f5f] p-6 text-white">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#d9e4ff]">
            Jurisdiction note
          </p>
          <p className="mt-4 text-sm leading-7 text-[#eef3ff]">
            Unless otherwise required by law, these terms are intended to be interpreted consistently with the laws of Victoria, Australia.
          </p>
        </section>
      </aside>
    </PublicShell>
  );
}
