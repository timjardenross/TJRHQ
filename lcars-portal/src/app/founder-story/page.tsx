import type { Metadata } from 'next';
import { PublicShell } from '@/components/public/PublicShell';
import { buildPublicMetadata } from '@/lib/public-site';

export const metadata: Metadata = buildPublicMetadata('/founder-story');

const storyBlocks = [
  `For most of my career, I have helped organisations prepare for, respond to, and recover from disruption. That work has involved major incident response, operational resilience, business continuity, and helping people keep functioning when pressure is real.`,
  `Outside of work, I have been learning a different kind of resilience.`,
  `For more than 20 years, I have lived with chronic spinal pain, surgery, setbacks, anxiety, and the ongoing work of rebuilding health, confidence, and identity. There was no single breakthrough and no quick fix. It has been a long process of learning what genuinely helps, letting go of what does not, and finding practical ways to keep moving forward when progress is slow.`,
  `TJR Mind & Body brings those two worlds together.`,
  `It is not about pretending everything is fine, pushing harder, or chasing unrealistic transformation. It is about practical tools, honest conversations, steady rebuilding, and resilience that can hold up in real life.`,
];

export default function FounderStoryPage() {
  return (
    <PublicShell
      path="/founder-story"
      eyebrow="Founder Story"
      title="Why TJR Mind & Body Exists"
      intro="A lived story about operational resilience, chronic pain, rebuilding, and the kind of support that feels useful when life is genuinely demanding."
    >
      <section className="rounded-[32px] border border-[#d9e1f0] bg-white p-6 shadow-[0_20px_60px_rgba(23,32,51,0.08)] sm:p-8">
        <div className="space-y-6">
          {storyBlocks.map((block) => (
            <p key={block} className="text-base leading-8 text-[#31415f] sm:text-lg">
              {block}
            </p>
          ))}
        </div>
      </section>

      <aside className="space-y-6">
        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#eaf0fb] p-6">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#566889]">
            What Shapes This Work
          </p>
          <ul className="mt-4 space-y-3 text-sm leading-7 text-[#31415f]">
            <li>Operational resilience and pressure-tested decision-making</li>
            <li>Long-term lived experience of pain, setbacks, and rebuilding</li>
            <li>Practical self-management over hype or all-or-nothing change</li>
            <li>Support that respects work, identity, and real-world demands</li>
          </ul>
        </section>

        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#1f2f5f] p-6 text-white">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#d9e4ff]">
            Working Principle
          </p>
          <p className="mt-4 text-base leading-7 text-[#eef3ff]">
            No hype. No big promises. Just practical tools, honest conversations, and steady progress.
          </p>
        </section>
      </aside>
    </PublicShell>
  );
}
