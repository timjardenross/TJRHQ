'use client';

/**
 * EDO Delivery surface (MSN-EDO-002). Makes the delivery pipeline visible:
 * where work is, where it's stuck, and how it's trending.
 */

import { DeliveryPanel } from '@/components/DeliveryPanel';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';

export default function DeliveryPage() {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-[10px] uppercase tracking-[0.3em] text-wb-ink2">
          MSN-EDO-001 · Engineering & Delivery
        </p>
        {/* text-engineering-on kept: real department identity (this is Engineering's
            delivery surface), not a decorative/status use — see Stream D report. */}
        <h1 className="font-sans text-2xl font-bold text-engineering-on">Delivery</h1>
        <p className="mt-1 max-w-2xl text-sm text-wb-ink/80 leading-relaxed">
          The Engineering & Delivery Officer keeps delivery visible, measured, and reuse-first —
          from request to operational capability, with the pipeline instrumented so bottlenecks
          surface instead of hiding.
        </p>
      </header>

      <DeliveryPanel />

      <WorkbenchPanel title="Operating model" eyebrow="EDO">
        <p className="text-sm text-wb-ink/80 leading-relaxed">
          One plan approval, one closure approval — no manual orchestration in between. The Officer
          analyses, reuses first, plans, executes on a branch, validates, reports real state, updates
          Command Memory, registers capability, and surfaces the change to the XO.
        </p>
        <p className="mt-2 text-[11px] text-wb-ink2">
          See <code>governance/ENGINEERING-DELIVERY-OFFICER-CHARTER.md</code> and{' '}
          <code>Missions/MSN-EDO-001/</code>.
        </p>
      </WorkbenchPanel>
    </div>
  );
}
