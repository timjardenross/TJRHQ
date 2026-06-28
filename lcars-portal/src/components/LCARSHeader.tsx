export interface LCARSHeaderProps {
  ship: string;
  registry: string;
  stardate: string;
  pageTitle?: string;
  condition?: string;
  readinessPercent?: number;
  missionStatus?: string;
}

export function LCARSHeader({
  ship,
  registry,
  stardate,
  pageTitle,
  condition = 'CONDITION GREEN',
  readinessPercent = 94,
  missionStatus = 'GREEN'
}: LCARSHeaderProps) {
  return (
    <header className="overflow-hidden rounded-lcars border border-edge bg-panel/70">
      <div className="flex flex-col gap-3 p-3 md:flex-row md:items-stretch md:gap-4">
        {/* LCARS elbow block */}
        <div className="flex items-end gap-2 shrink-0">
          <div className="h-14 w-24 rounded-bl-lcars rounded-tl-lcars bg-command" />
          <div className="h-8 w-10 rounded-md bg-engineering" />
          <div className="h-6 w-6 rounded-md bg-medical" />
        </div>

        {/* Page title + ship identity */}
        <div className="flex flex-1 flex-col justify-center min-w-0">
          {pageTitle && (
            <h1 className="text-xl font-bold text-command-on md:text-2xl uppercase tracking-widest">
              {pageTitle}
            </h1>
          )}
          <p className="lcars-readout truncate">
            {ship} · {registry}
          </p>
        </div>

        {/* Stat blocks */}
        <div className="hidden lg:flex items-stretch gap-0 divide-x divide-edge">
          <div className="flex flex-col justify-center pr-5">
            <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">
              Operational Readiness
            </p>
            <p className="font-lcars text-2xl font-bold text-status leading-none mt-0.5">
              {readinessPercent}%
            </p>
          </div>
          <div className="flex flex-col justify-center px-5">
            <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">
              Mission Status
            </p>
            <p className="font-lcars text-2xl font-bold text-status leading-none mt-0.5">
              {missionStatus}
            </p>
          </div>
          <div className="flex flex-col justify-center pl-5">
            <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">
              Stardate
            </p>
            <p className="font-lcars text-lg font-bold text-command leading-none mt-0.5">
              {stardate}
            </p>
            <p className="text-[10px] uppercase tracking-[0.15em] text-lcars-muted mt-0.5">
              Ship Time
            </p>
          </div>
        </div>

        {/* Condition badge */}
        <div className="flex items-center shrink-0">
          <span className="lcars-pill bg-status/20 text-status">{condition}</span>
        </div>
      </div>
      <div className="flex gap-1 px-3 pb-3">
        <div className="lcars-bar flex-[3] bg-command" />
        <div className="lcars-bar flex-1 bg-engineering" />
        <div className="lcars-bar flex-1 bg-operations" />
        <div className="lcars-bar flex-1 bg-medical" />
        <div className="lcars-bar flex-1 bg-science" />
        <div className="lcars-bar flex-[2] bg-status" />
      </div>
    </header>
  );
}
