/**
 * LCARSHeader — top command bar with the signature LCARS elbow + readouts.
 * Reusable: pass ship / registry / stardate (defaults pull from mock data).
 */
export interface LCARSHeaderProps {
  ship: string;
  registry: string;
  stardate: string;
  condition?: string;
}

export function LCARSHeader({
  ship,
  registry,
  stardate,
  condition = 'CONDITION GREEN'
}: LCARSHeaderProps) {
  return (
    <header className="overflow-hidden rounded-lcars border border-edge bg-panel/70">
      <div className="flex flex-col gap-3 p-3 md:flex-row md:items-stretch md:gap-4">
        {/* LCARS elbow block */}
        <div className="flex items-end gap-2">
          <div className="h-14 w-24 rounded-bl-lcars rounded-tl-lcars bg-command" />
          <div className="h-8 w-10 rounded-md bg-engineering" />
          <div className="h-6 w-6 rounded-md bg-medical" />
        </div>

        <div className="flex flex-1 flex-col justify-center">
          <h1 className="text-xl font-bold text-command md:text-2xl">{ship}</h1>
          <p className="lcars-readout">
            {registry} · STARDATE {stardate}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="lcars-pill bg-status/20 text-status">{condition}</span>
          <span className="lcars-pill bg-edge/40 text-lcars-muted">
            LCARS · PHASE 1
          </span>
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
