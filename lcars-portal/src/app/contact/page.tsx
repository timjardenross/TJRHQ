import type { Metadata } from 'next';
import { PublicShell } from '@/components/public/PublicShell';
import { CONTACT_RESPONSE_TIME, buildPublicMetadata } from '@/lib/public-site';

export const metadata: Metadata = buildPublicMetadata('/contact');

const contactOptions = [
  {
    title: 'General support',
    detail: 'Questions about the approach, the brand, or whether this work feels relevant to what you are navigating.',
  },
  {
    title: 'Coaching and education',
    detail: 'Enquiries about practical resilience coaching, self-management support, or tailored education conversations.',
  },
  {
    title: 'Discovery conversation',
    detail: 'A calm first conversation to understand what is going on and what kind of support may make sense next.',
  },
  {
    title: 'Partnerships or speaking',
    detail: 'Opportunities related to practical resilience, operational pressure, rebuilding, or lived-experience-informed education.',
  },
];

export default function ContactPage() {
  return (
    <PublicShell
      path="/contact"
      eyebrow="Contact"
      title="Start With a Simple Conversation"
      intro="If you want to ask a question, explore support, or enquire about a discovery conversation, this is the best place to start."
    >
      <section className="rounded-[32px] border border-[#d9e1f0] bg-white p-6 shadow-[0_20px_60px_rgba(23,32,51,0.08)] sm:p-8">
        <p className="text-base leading-8 text-[#31415f] sm:text-lg">
          The easiest way to get in touch is by email. You are welcome to share a little about what you are navigating, what kind of support you are looking for, and any questions you want answered first.
        </p>

        <div className="mt-8 rounded-[28px] border border-[#dbe3f3] bg-[#f7f9fd] p-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#566889]">
            Email
          </p>
          <a
            href="mailto:support@tjrmindbody.com"
            className="mt-3 inline-block text-2xl font-semibold tracking-[-0.02em] text-[#243b7a] underline decoration-[#b7c7ec] underline-offset-4"
          >
            support@tjrmindbody.com
          </a>
          <p className="mt-3 text-sm leading-7 text-[#5a6780]">
            If it feels like a good fit, a discovery conversation can be arranged from there.
          </p>
        </div>

        <div className="mt-6 rounded-[28px] border border-[#d9e1f0] bg-[#fcfdff] p-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#566889]">
            Expected response time
          </p>
          <p className="mt-3 text-sm leading-7 text-[#4b5c78]">
            {CONTACT_RESPONSE_TIME}
          </p>
          <p className="mt-2 text-sm leading-7 text-[#4b5c78]">
            If your enquiry relates to urgent medical or mental health support, please contact an appropriate clinician, crisis line, or emergency service instead of relying on email.
          </p>
        </div>
      </section>

      <aside className="space-y-6">
        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#eaf0fb] p-6">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#566889]">
            Common Reasons People Reach Out
          </p>
          <div className="mt-4 space-y-4">
            {contactOptions.map((option) => (
              <div key={option.title} className="rounded-[24px] border border-white/70 bg-white/70 p-4">
                <h2 className="text-base font-semibold text-[#1e2942]">{option.title}</h2>
                <p className="mt-2 text-sm leading-7 text-[#4b5c78]">{option.detail}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#1f2f5f] p-6 text-white">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#d9e4ff]">
            Plain-English Approach
          </p>
          <p className="mt-4 text-sm leading-7 text-[#eef3ff]">
            The tone here is steady, practical, and human. The aim is to be useful, not overwhelming.
          </p>
        </section>
      </aside>
    </PublicShell>
  );
}
