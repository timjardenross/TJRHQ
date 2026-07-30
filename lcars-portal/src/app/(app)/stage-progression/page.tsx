import { LCARSPanel } from '@/components/LCARSPanel';

// This page previously rendered a stage number, stability signal, criteria
// checklist, and assessment log that were 100% hardcoded (src/lib/mockData.ts)
// regardless of live data availability - Captain-facing content presented as
// real when it was not. Retired rather than left live per the Starship
// rewrite's Phase 0 finding (docs/INVENTORY.md) - a placeholder must never be
// shown as if it were real. Not replaced with a new real version here; a
// genuine stage-progression experience, if wanted, is a future decision, not
// a fix bundled into this retirement.

export default function StageProgressionPage() {
  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel title="Stage Progression" accent="medical" eyebrow="Retired — prototype data">
        <p className="text-sm text-lcars-text/90 leading-relaxed">
          This page is retired. The stage, stability signal, and assessment log it used to show
          were placeholder data, not a live assessment - they have been removed rather than left
          up as if they were real.
        </p>
        <p className="mt-3 text-sm text-lcars-text/90 leading-relaxed">
          Real recovery and readiness data is still available on the Health Centre and Physical
          Readiness pages.
        </p>
      </LCARSPanel>
    </div>
  );
}
