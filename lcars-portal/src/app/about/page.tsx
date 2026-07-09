import type { Metadata } from 'next';
import { PublicShell } from '@/components/public/PublicShell';
import { buildPublicMetadata } from '@/lib/public-site';

export const metadata: Metadata = buildPublicMetadata('/about');

const principles = [
  {
    title: 'Practical, not performative',
    detail:
      'The focus is on tools, reflection, and support that can actually be used in the middle of work, pain, stress, and uncertainty.',
  },
  {
    title: 'Steady rebuilding',
    detail:
      'This work is built around consistency, capacity, and sustainable progress rather than hype, pressure, or all-or-nothing change.',
  },
  {
    title: 'Real-world resilience',
    detail:
      'The approach recognises that resilience has to function in busy lives, demanding jobs, changing health, and messy seasons of life.',
  },
];

export default function AboutPage() {
  return (
    <PublicShell
      path="/about"
      eyebrow="About"
      title="A practical resilience brand built for real-life pressure"
      intro="TJR Mind & Body combines coaching, education, and lived perspective to help people build resilience that feels honest, useful, and sustainable."
    >
      <section className="space-y-6 rounded-[32px] border border-[#d9e1f0] bg-white p-6 shadow-[0_20px_60px_rgba(23,32,51,0.08)] sm:p-8">
        <div>
          <h2 className="text-2xl font-semibold normal-case tracking-[-0.02em] text-[#1d2840]">
            What TJR Mind &amp; Body is
          </h2>
          <p className="mt-4 text-base leading-8 text-[#31415f] sm:text-lg">
            TJR Mind &amp; Body is a practical resilience coaching and education brand. It is designed for people navigating real pressure: chronic stress, burnout, chronic pain, disruption, overload, and the slower work of rebuilding after things have shifted.
          </p>
        </div>

        <div>
          <h2 className="text-2xl font-semibold normal-case tracking-[-0.02em] text-[#1d2840]">
            Who this work is for
          </h2>
          <p className="mt-4 text-base leading-8 text-[#31415f] sm:text-lg">
            This work is especially relevant for people who are trying to keep functioning while carrying more than usual, whether that pressure is personal, physical, emotional, or professional. It is for people who want grounded support rather than motivational noise.
          </p>
        </div>

        <div>
          <h2 className="text-2xl font-semibold normal-case tracking-[-0.02em] text-[#1d2840]">
            How the work is shaped
          </h2>
          <p className="mt-4 text-base leading-8 text-[#31415f] sm:text-lg">
            The approach draws from operational resilience, business continuity thinking, lived experience of chronic pain and rebuilding, and a strong preference for plain-English tools that respect people&apos;s actual lives.
          </p>
        </div>
      </section>

      <aside className="space-y-6">
        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#eaf0fb] p-6">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#566889]">
            Three guiding principles
          </p>
          <div className="mt-4 space-y-4">
            {principles.map((item) => (
              <div key={item.title} className="rounded-[24px] border border-white/80 bg-white/70 p-4">
                <h2 className="text-base font-semibold normal-case tracking-normal text-[#1d2840]">
                  {item.title}
                </h2>
                <p className="mt-2 text-sm leading-7 text-[#4b5c78]">{item.detail}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#1f2f5f] p-6 text-white">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#d9e4ff]">
            Important note
          </p>
          <p className="mt-4 text-sm leading-7 text-[#eef3ff]">
            TJR Mind &amp; Body offers coaching and education. It does not replace medical care, mental health care, diagnosis, or emergency support.
          </p>
        </section>
      </aside>
    </PublicShell>
  );
}
