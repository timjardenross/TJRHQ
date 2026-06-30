import { StatusBadge } from '@/components/StatusBadge';
import { LCARSPanel } from '@/components/LCARSPanel';
import { DEPARTMENTS, toneClasses } from '@/lib/departments';
import { knowledgeArticles } from '@/lib/mockData';

export const metadata = { title: 'Knowledge Base · LCARS Portal' };

// ── Shared primitives ─────────────────────────────────────────────────────────

function Panel({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-lcars border border-edge bg-panel/60 p-3 ${className}`}>
      {children}
    </div>
  );
}

function SectionHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-[11px] font-bold uppercase tracking-[0.25em] text-lcars-muted">{title}</h2>
      {action}
    </div>
  );
}

// ── Derived data ──────────────────────────────────────────────────────────────

function getCategoryMap() {
  const map = new Map<string, { count: number; dept: string }>();
  for (const a of knowledgeArticles) {
    const existing = map.get(a.category);
    if (existing) existing.count++;
    else map.set(a.category, { count: 1, dept: a.department });
  }
  return map;
}

const recentlySorted = [...knowledgeArticles].sort(
  (a, b) => new Date(b.updated).getTime() - new Date(a.updated).getTime()
);

// ── Quick Access — pinned docs ────────────────────────────────────────────────

const PINNED_DOCS = [
  {
    id: 'CD-055',
    title: 'Directive 055 — Captain Capacity First',
    category: 'Governance',
    description: 'Core operating doctrine. Starship Endeavour exists to increase Captain Capacity.',
    tone: 'text-medical border-medical/40 bg-medical/5',
    path: 'knowledge/Captains-Directives.md',
  },
  {
    id: 'ROS-001',
    title: 'Recovery Operating System v1.1',
    category: 'Medical',
    description: 'Four-stage recovery model. Transitions are recognised, not achieved.',
    tone: 'text-command border-command/40 bg-command/5',
    path: 'knowledge/ROS-001-Recovery-Operating-System.md',
  },
  {
    id: 'CD-001',
    title: 'Captain\'s Directives Registry',
    category: 'Governance',
    description: 'Enduring instructions governing behaviour, priorities, and evolution of USS TJR.',
    tone: 'text-science border-science/40 bg-science/5',
    path: 'knowledge/Captains-Directives.md',
  },
];

function QuickAccess() {
  return (
    <LCARSPanel
      title="Quick Access"
      accent="science"
      eyebrow="Pinned — key doctrine documents"
    >
      <div className="grid gap-3 sm:grid-cols-3">
        {PINNED_DOCS.map((doc) => (
          <div
            key={doc.id}
            className={`rounded-lcars border p-4 ${doc.tone}`}
          >
            <p className="font-mono text-[10px] text-lcars-muted mb-1">{doc.id}</p>
            <p className="text-sm font-semibold text-lcars-text leading-snug">{doc.title}</p>
            <p className="text-xs text-lcars-muted/80 mt-1.5 leading-relaxed">{doc.description}</p>
            <p className="text-[10px] font-mono text-lcars-muted/50 mt-2 truncate">{doc.path}</p>
          </div>
        ))}
      </div>
    </LCARSPanel>
  );
}

// ── KB Stats header ───────────────────────────────────────────────────────────

function KBStats() {
  const categoryMap = getCategoryMap();
  const recentCutoff = new Date();
  recentCutoff.setDate(recentCutoff.getDate() - 7);
  const recentCount = knowledgeArticles.filter(
    (a) => new Date(a.updated) >= recentCutoff
  ).length;

  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-0 divide-x divide-edge">
        <div className="flex flex-col pr-6">
          <span className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Total Entries</span>
          <span className="font-lcars text-2xl font-bold leading-none text-science mt-0.5">
            {knowledgeArticles.length}
          </span>
        </div>
        <div className="flex flex-col px-6">
          <span className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Categories</span>
          <span className="font-lcars text-2xl font-bold leading-none text-command mt-0.5">
            {categoryMap.size}
          </span>
        </div>
        <div className="flex flex-col pl-6">
          <span className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Updated (7d)</span>
          <span className="font-lcars text-2xl font-bold leading-none text-status mt-0.5">
            {recentCount}
          </span>
        </div>
      </div>
    </Panel>
  );
}

// ── Category sidebar ──────────────────────────────────────────────────────────

function CategoryList() {
  const categoryMap = getCategoryMap();
  const CATEGORY_TONE: Record<string, string> = {
    'Architecture Decision Record': 'text-command border-command',
    'Governance': 'text-operations border-operations',
    'Engineering': 'text-engineering border-engineering',
    'Science': 'text-science border-science',
    'Operations': 'text-operations border-operations',
    'Medical': 'text-medical border-medical',
  };
  return (
    <Panel>
      <SectionHeader title="Categories" />
      <ul className="flex flex-col gap-2">
        {Array.from(categoryMap.entries()).map(([cat, { count }]) => {
          const cls = CATEGORY_TONE[cat] ?? 'text-lcars-muted border-edge';
          return (
            <li
              key={cat}
              className={`flex items-center justify-between rounded-md border bg-panel-2/60 px-3 py-2 ${cls.split(' ')[1]}`}
            >
              <span className={`text-[11px] font-semibold uppercase tracking-wide ${cls.split(' ')[0]}`}>
                {cat}
              </span>
              <span className={`font-mono text-xs font-bold ${cls.split(' ')[0]}`}>{count}</span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

// ── Recent updates strip ──────────────────────────────────────────────────────

function RecentUpdates() {
  const recent = recentlySorted.slice(0, 3);
  return (
    <Panel>
      <SectionHeader title="Recently Updated" />
      <ul className="flex flex-col gap-2">
        {recent.map((a) => {
          const dept = DEPARTMENTS[a.department];
          return (
            <li key={a.id} className="flex items-center gap-3 rounded-md border border-edge bg-panel-2/60 p-2">
              <span className={`h-2 w-2 shrink-0 rounded-full ${dept.bg}`} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[11px] font-medium text-lcars-text">{a.title}</p>
                <p className="text-[10px] text-lcars-muted">{a.owner}</p>
              </div>
              <span className="shrink-0 font-mono text-[10px] text-lcars-muted">{a.updated}</span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

// ── Article grid ──────────────────────────────────────────────────────────────

function ArticleGrid() {
  return (
    <Panel>
      <SectionHeader
        title="All Articles"
        action={<StatusBadge label={`${knowledgeArticles.length} entries`} tone="science" />}
      />
      <div className="grid gap-3 md:grid-cols-2">
        {recentlySorted.map((a) => {
          const dept = DEPARTMENTS[a.department];
          return (
            <article
              key={a.id}
              className="flex flex-col gap-2 rounded-lcars border border-edge bg-panel-2/60 p-3"
              style={{ borderLeftColor: dept.hex, borderLeftWidth: 4 }}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="font-mono text-xs text-lcars-muted">{a.id}</span>
                <span className={`text-[10px] uppercase tracking-wider ${dept.text}`}>
                  {a.category}
                </span>
              </div>
              <h3 className="text-sm font-semibold normal-case text-lcars-text">{a.title}</h3>
              <p className="text-xs leading-relaxed text-lcars-muted">{a.excerpt}</p>
              <div className="mt-auto flex items-center justify-between text-[10px] text-lcars-muted">
                <span>{a.owner}</span>
                <span className="font-mono">Updated {a.updated}</span>
              </div>
            </article>
          );
        })}
      </div>
    </Panel>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function KnowledgeBasePage() {
  return (
    <div className="flex flex-col gap-4">
      <QuickAccess />
      <KBStats />

      <div className="grid gap-4 xl:grid-cols-[220px_1fr]">
        <div className="flex flex-col gap-4">
          <CategoryList />
          <RecentUpdates />
        </div>
        <ArticleGrid />
      </div>
    </div>
  );
}
