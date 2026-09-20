import Link from 'next/link';

export function DataAvailabilityNotice({
  sources,
  className = '',
}: {
  sources: string[];
  className?: string;
}) {
  const uniqueSources = [...new Set(sources.filter(Boolean))];
  if (uniqueSources.length === 0) return null;

  return (
    <aside
      role="status"
      aria-label="Data availability"
      className={`rounded-xl border border-wb-warn/60 bg-wb-warn/10 px-4 py-3 text-sm ${className}`}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
        <div>
          <p className="font-semibold text-wb-warn">Some live data is unavailable</p>
          <p className="mt-1 text-xs leading-relaxed text-wb-ink2">
            This is not confirmation that nothing has changed. The page is showing the last trustworthy interpretation available.
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
