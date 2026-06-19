import { LCARSPanel } from '@/components/LCARSPanel';
import { intelligenceBrief } from '@/lib/mockData';

export const metadata = { title: 'XO Brief · LCARS Portal' };

function formatTime(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toUTCString().replace('GMT', 'UTC');
}

export default function XOBriefPage() {
  const brief = intelligenceBrief;
  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title={brief.title}
        accent="science"
        eyebrow={`Generated ${formatTime(brief.generated)}`}
      >
        <p className="text-sm text-lcars-text/90">{brief.summary}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {brief.themes.map((t) => (
            <span
              key={t}
              className="rounded-full border border-science bg-science/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-science"
            >
              {t}
            </span>
          ))}
        </div>
      </LCARSPanel>

      <div className="grid gap-4 md:grid-cols-2">
        {brief.sections.map((s) => (
          <LCARSPanel key={s.heading} title={s.heading} accent="science">
            <p className="text-sm leading-relaxed text-lcars-text/90">{s.body}</p>
          </LCARSPanel>
        ))}
      </div>
    </div>
  );
}
