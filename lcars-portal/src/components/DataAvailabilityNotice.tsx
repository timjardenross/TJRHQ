import Link from 'next/link';

export function DataAvailabilityNotice({
  sources,
  state = 'unavailable',
  className = '',
}: {
  sources: string[];
  state?: 'empty' | 'no-action' | 'unavailable' | 'stale';
  className?: string;
}) {
  const uniqueSources = [...new Set(sources.filter(Boolean))];
  if (uniqueSources.length === 0) return null;

  const copy = {
    empty: { title: 'No records found', detail: 'There is currently no matching record to show.' },
    'no-action': { title: 'Nothing needs action now', detail: 'The monitored information is available and no action is currently required.' },
    unavailable: { title: 'Some live data is unavailable', detail: 'This is not confirmation that nothing has changed. The page is showing the last trustworthy interpretation available.' },
    stale: { title: 'Some data may be stale', detail: 'The source responded, but its latest collection time is outside the expected freshness window.' },
  }[state];

  return (
    <aside
      role="status"
      aria-label="Data availability"
      className={`rounded-xl border border-wb-warn/60 bg-wb-warn/10 px-4 py-3 text-sm ${className}`}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
        <div>
      <p className="font-semibold text-wb-warn">{copy.title}</p>
      <p className="mt-1 text-xs leading-relaxed text-wb-ink2">
            {copy.detail}
          </p>
          <p className="mt-2 text-[11px] text-wb-ink2">
            Affected: {uniqueSources.join(' · ')}
          </p>
        </div>
        <Link
          href="/agent-status-workbench"
          className="shrink-0 text-xs font-semibold text-wb-warn underline underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-warn"
        >
          Check HQ Status →
        </Link>
      </div>
    </aside>
  );
}
