import { LCARSPanel } from '@/components/LCARSPanel';
import { knowledgeArticles } from '@/lib/mockData';
import { DEPARTMENTS } from '@/lib/departments';

export const metadata = { title: 'Knowledge Base · LCARS Portal' };

export default function KnowledgeBasePage() {
  const categories = Array.from(
    new Set(knowledgeArticles.map((a) => a.category))
  );

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Knowledge Base"
        accent="science"
        eyebrow="Computer Core Library"
      >
        <p className="text-sm text-lcars-text/90">
          ADRs, governance standards and playbooks. Phase 2 sources these from
          the knowledge/ directory and the Supabase knowledge prototype.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {categories.map((c) => (
            <span
              key={c}
              className="rounded-full border border-edge px-3 py-1 text-[11px] uppercase tracking-wider text-lcars-muted"
            >
              {c}
            </span>
          ))}
        </div>
      </LCARSPanel>

      <LCARSPanel title="Articles" accent="science" eyebrow={`${knowledgeArticles.length} entries`}>
        <div className="grid gap-3 md:grid-cols-2">
          {knowledgeArticles.map((a) => {
            const dept = DEPARTMENTS[a.department];
            return (
              <article
                key={a.id}
                className={`flex flex-col gap-2 rounded-lcars border-l-4 ${dept.border} border-edge bg-panel-2/60 p-3`}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="font-mono text-xs text-lcars-muted">{a.id}</span>
                  <span className={`text-[10px] uppercase tracking-wider ${dept.text}`}>
                    {a.category}
                  </span>
                </div>
                <h3 className="text-sm font-semibold normal-case text-lcars-text">
                  {a.title}
                </h3>
                <p className="text-xs text-lcars-muted">{a.excerpt}</p>
                <div className="mt-auto flex items-center justify-between text-[10px] text-lcars-muted">
                  <span>{a.owner}</span>
                  <span className="font-mono">Updated {a.updated}</span>
                </div>
              </article>
            );
          })}
        </div>
      </LCARSPanel>
    </div>
  );
}
