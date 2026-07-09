import type { Metadata } from 'next';
import Link from 'next/link';
import { PublicShell } from '@/components/public/PublicShell';
import { buildPublicMetadata } from '@/lib/public-site';

export const metadata: Metadata = buildPublicMetadata('/');

const pillars = [
  {
    title: 'Support',
    detail: 'Grounded support for people navigating chronic stress, burnout, pain, disruption, and demanding seasons of life.',
  },
  {
    title: 'Coaching',
    detail: 'Practical resilience coaching focused on useful next steps, not motivational noise or all-or-nothing change.',
  },
  {
    title: 'Education',
    detail: 'Plain-English tools and frameworks that help people rebuild capacity, confidence, and steadier day-to-day systems.',
  },
];

const principles = [
  'Practical resilience over performative positivity',
  'Steady rebuilding over quick-fix transformation',
  'Self-management tools that can hold up in real life',
];

export default function Home() {
  return (
    <PublicShell
      path="/"
      eyebrow="TJR Mind & Body"
      title="Practical resilience coaching and education for real-life pressure"
      intro="Built for people navigating chronic stress, pain, burnout, disruption, and the slow work of rebuilding. The focus here is practical support, steady progress, and resilience that can hold up in real life."
    >
      <section className="space-y-6">
        <div className="rounded-[32px] border border-[#d9e1f0] bg-white p-6 shadow-[0_20px_60px_rgba(23,32,51,0.08)] sm:p-8">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#566889]">
            Why This Work Exists
          </p>
          <p className="mt-4 text-base leading-8 text-[#31415f] sm:text-lg">
            TJR Mind &amp; Body exists at the intersection of two kinds of resilience: the kind built through operational pressure at work, and the much more personal kind required when health, energy, confidence, and identity are shaken up.
          </p>
          <p className="mt-4 text-base leading-8 text-[#31415f] sm:text-lg">
            It is not about pretending everything is fine or pushing harder. It is about practical tools, honest conversations, and steady rebuilding that feels sustainable.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              aria-label="Read the TJR Mind & Body founder story"
              href="/founder-story"
              className="rounded-full bg-[#243b7a] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#1e315f]"
            >
              Read the founder story
            </Link>
            <Link
              aria-label="Contact TJR Mind & Body"
              href="/contact"
              className="rounded-full border border-[#c9d5ee] px-5 py-3 text-sm font-semibold text-[#24304b] transition hover:border-[#243b7a] hover:text-[#243b7a]"
            >
              Contact TJR Mind &amp; Body
            </Link>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {pillars.map((pillar) => (
            <article key={pillar.title} className="rounded-[28px] border border-[#d9e1f0] bg-[#eaf0fb] p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#566889]">
                {pillar.title}
              </p>
              <p className="mt-3 text-sm leading-7 text-[#31415f]">{pillar.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <aside className="space-y-6">
        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#1f2f5f] p-6 text-white">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#d9e4ff]">
            Founder Focus
          </p>
          <p className="mt-4 text-base leading-7 text-[#eef3ff]">
            Tim Jarden-Ross brings together lived experience of long-term pain and rebuilding with a career spent helping organisations function under real pressure.
          </p>
          <Link
            aria-label="Explore the TJR Mind & Body founder story"
            href="/founder-story"
            className="mt-5 inline-block text-sm font-semibold text-white underline decoration-[#93a9e8] underline-offset-4"
          >
            Explore the full story
          </Link>
        </section>

        <section className="rounded-[32px] border border-[#d9e1f0] bg-white p-6">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#566889]">
            What You Will Find Here
          </p>
          <ul className="mt-4 space-y-3 text-sm leading-7 text-[#31415f]">
            {principles.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      </aside>
    </PublicShell>
  );
}
