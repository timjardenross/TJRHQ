import Link from 'next/link';
import { WorkbenchShell } from '@/components/ui';

const ITEMS = [
  ['critical', 'TIME-CRITICAL', 'Recovery posture: REST', 'The nervous system needs rest today. No operational load recommended.', 'Review'],
  ['attention', 'DECIDE', 'The Telstra outage is a stark reminder', 'One item is QA’d and ready for your publish decision.', 'Publish / Schedule'],
  ['review', 'REVIEW', 'Nervous-system load remains elevated', 'Wellness risk flags raised.', 'Review'],
  ['info', 'REVIEW', '2 notes ready for routing', 'Captured in the Log, reviewed, waiting on your routing decision.', 'Review'],
] as const;

const rail = { critical: 'bg-wb-crit', attention: 'bg-wb-warn', review: 'bg-wb-sage', info: 'bg-sky-300' };
const label = { critical: 'text-wb-crit', attention: 'text-wb-warn', review: 'text-wb-sage', info: 'text-sky-300' };

export default function BlackCaptainChairPreview() {
  return (
    <WorkbenchShell title="Captain’s Chair" eyebrow="Executive command surface · Endeavour 27 dark reference" tagline="A calm mind. A stronger you. A brighter tomorrow." back={{ href: '/captains-chair-workbench', label: 'Captain’s Chair' }} mode="command" wide>
      <div className="space-y-4">
        <section className="relative overflow-hidden rounded-2xl border border-wb-line bg-wb-surface px-6 py-7 shadow-[0_18px_50px_rgba(0,0,0,0.24)] sm:px-8">
          <div className="absolute inset-y-0 right-0 w-2/3 bg-[radial-gradient(ellipse_at_75%_20%,rgba(106,190,255,0.32),transparent_48%),linear-gradient(135deg,transparent_15%,rgba(13,44,68,0.8))]" aria-hidden />
          <div className="absolute -right-16 top-8 h-32 w-3/5 rounded-[50%] border-b-2 border-sky-300/70 shadow-[0_12px_40px_rgba(90,180,255,0.24)]" aria-hidden />
          <div className="relative max-w-2xl">
            <p className="text-[10px] font-semibold uppercase tracking-[0.25em] text-wb-ink2">What kind of day is this?</p>
            <h2 className="mt-1 text-4xl font-semibold tracking-[0.12em] text-wb-ink">TODAY</h2>
            <div className="my-3 h-px w-2/3 bg-wb-line" />
            <p className="text-3xl font-bold tracking-[0.04em] text-wb-crit">RESPOND</p>
            <p className="mt-1 text-sm text-wb-ink2">4 things genuinely need you today.</p>
            <div className="mt-5 flex flex-wrap gap-2 text-[11px] font-medium">
              <span className="rounded-full border border-wb-crit px-3 py-1 text-wb-crit">Capacity: Red (1)</span><span className="rounded-full border border-wb-line px-3 py-1 text-wb-ink2">Interrupts: Unknown</span><span className="rounded-full border border-wb-sage px-3 py-1 text-wb-sage">Alerts: Clear</span><span className="rounded-full border border-wb-warn px-3 py-1 text-wb-warn">HQ: Degraded</span><span className="rounded-full border border-wb-warn px-3 py-1 text-wb-warn">Risk: Amber</span>
            </div>
          </div>
        </section>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(270px,0.9fr)]">
          <section className="rounded-2xl border border-wb-line bg-wb-surface p-4 sm:p-5">
            <div className="mb-4 flex items-end justify-between gap-4 border-b border-wb-line pb-3"><div><p className="text-[10px] uppercase tracking-[0.22em] text-wb-ink2">4 decisions · 2 reviews</p><h2 className="mt-1 text-xl font-semibold tracking-[0.1em] text-wb-ink">NEEDS YOU</h2></div><span className="text-[11px] text-wb-ink2">Sort: Priority⌄</span></div>
            <div className="space-y-2.5">
              {ITEMS.map(([tone, eyebrow, title, detail, action]) => <article key={title} className="relative overflow-hidden rounded-xl border border-wb-line bg-wb-bg p-3 pl-5 sm:p-4 sm:pl-6"><span className={`absolute inset-y-0 left-0 w-1 ${rail[tone]}`} aria-hidden /><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><p className={`text-[10px] font-bold uppercase tracking-[0.18em] ${label[tone]}`}>{eyebrow}</p><h3 className="mt-1 text-sm font-semibold text-wb-ink sm:text-base">{title}</h3><p className="mt-1 text-xs leading-relaxed text-wb-ink2">{detail}</p></div><Link href="/captains-chair-workbench" className="inline-flex shrink-0 items-center justify-center rounded-md border border-wb-line bg-wb-surface-raised px-3 py-2 text-[11px] font-semibold text-wb-ink hover:border-wb-sand focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sand">{action} →</Link></div></article>)}
            </div>
          </section>

          <div className="space-y-4">{[['REMEMBER', 'Nothing waiting to come back to you.', 'Unavailable right now. Remember.'], ['INTELLIGENCE', 'Intelligence unavailable', 'Brief coverage is unavailable right now — this is not confirmation that nothing has changed.'], ['CAPACITY', 'RECOVER', 'Capacity is depleted or recovery debt is high. Recovery is the primary objective.'], ['AHEAD', 'Next 24–48 hours', 'Calendar unavailable — see console for detail.']].map(([title, headline, body]) => <section key={title} className="rounded-2xl border border-wb-line bg-wb-surface p-4"><h2 className="border-b border-wb-line pb-2 text-sm font-semibold tracking-[0.16em] text-wb-ink">{title}</h2><p className="mt-3 text-sm font-semibold text-wb-ink">{headline}</p><p className="mt-1 text-xs leading-relaxed text-wb-ink2">{body}</p></section>)}</div>
        </div>

        <section className="rounded-2xl border border-wb-line bg-wb-surface p-4 sm:p-5"><div className="flex items-center justify-between border-b border-wb-line pb-3"><h2 className="text-sm font-semibold tracking-[0.16em] text-wb-ink">SYSTEM STATUS</h2><span className="text-[11px] text-wb-ink2">No action required yet →</span></div><div className="grid gap-3 pt-4 sm:grid-cols-4">{['HQ · Degraded', 'Life Support · Nominal', 'Comms · Nominal', 'Data Core · Nominal'].map((item) => <div key={item} className="border-l border-wb-line pl-3 text-xs text-wb-ink2"><span className="mr-2 inline-block h-2 w-2 rounded-full bg-wb-sage" />{item}</div>)}</div></section>
      </div>
    </WorkbenchShell>
  );
}
