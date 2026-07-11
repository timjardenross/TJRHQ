import type { Metadata } from 'next';
import { PublicShell } from '@/components/public/PublicShell';
import { buildPublicMetadata } from '@/lib/public-site';

export const metadata: Metadata = buildPublicMetadata('/disclaimer');

const disclaimers = [
  {
    title: 'Educational and coaching scope',
    body: `The content on this website is provided for general educational and coaching-focused purposes. It is intended to support reflection, practical resilience, and informed conversations. It is not treatment, therapy, diagnosis, or medical advice.`,
  },
  {
    title: 'Not a substitute for professional care',
    body: `Information on this website should not replace advice from your doctor, psychologist, allied health practitioner, lawyer, financial adviser, or other qualified professional who understands your personal circumstances.`,
  },
  {
    title: 'Health and wellbeing information',
    body: `If this website discusses stress, pain, rebuilding, or self-management concepts, that information remains general in nature. Decisions about symptoms, medication, diagnosis, treatment, mental health concerns, or urgent care should be made with an appropriate clinician.`,
  },
  {
    title: 'Emergency situations',
    body: `If you are experiencing a medical emergency, are in immediate danger, or need urgent mental health support, contact emergency services or an appropriate crisis or healthcare provider immediately. Do not rely on this website or email communication for urgent assistance.`,
  },
  {
    title: 'No guaranteed outcomes',
    body: `Website content, educational tools, or future coaching conversations do not guarantee specific results. What helps one person may not be right for another, and outcomes depend on many factors outside the website&apos;s control.`,
  },
];

export default function DisclaimerPage() {
  return (
    <PublicShell
      path="/disclaimer"
      eyebrow="Website Disclaimer"
      title="Website Disclaimer"
      intro="This page clarifies the scope of the public TJR Mind & Body website and the limits of the information shared here."
    >
      <section className="rounded-[32px] border border-[#d9e1f0] bg-white p-6 shadow-[0_20px_60px_rgba(23,32,51,0.08)] sm:p-8">
        <div className="space-y-8">
          {disclaimers.map((item) => (
            <section key={item.title}>
              <h2 className="text-2xl font-semibold normal-case tracking-[-0.02em] text-[#1d2840]">
                {item.title}
              </h2>
              <p className="mt-3 text-base leading-8 text-[#31415f]">{item.body}</p>
            </section>
          ))}
        </div>
      </section>

      <aside className="space-y-6">
        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#eaf0fb] p-6">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#566889]">
            Plain-language summary
          </p>
          <p className="mt-4 text-sm leading-7 text-[#4b5c78]">
            TJR Mind &amp; Body is centred on education and coaching. It is not a substitute for clinicians or emergency services.
          </p>
        </section>

        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#1f2f5f] p-6 text-white">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#d9e4ff]">
            If in doubt
          </p>
          <p className="mt-4 text-sm leading-7 text-[#eef3ff]">
            Seek advice from an appropriately qualified health professional or other relevant adviser before acting on information from this website.
          </p>
        </section>
      </aside>
    </PublicShell>
  );
}
