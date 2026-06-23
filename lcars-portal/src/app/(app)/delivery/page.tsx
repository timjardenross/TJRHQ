'use client';

/**
 * EDO Delivery surface (MSN-EDO-002). Makes the delivery pipeline visible:
 * where work is, where it's stuck, and how it's trending.
 */

import { DeliveryPanel } from '@/components/DeliveryPanel';
import { LCARSPanel } from '@/components/LCARSPanel';

export default function DeliveryPage() {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted">
          MSN-EDO-001 · Engineering & Delivery
        </p>
        <h1 className="font-lcars text-2xl font-bold text-engineering">Delivery</h1>
        <p className="mt-1 max-w-2xl text-sm text-lcars-text/80 leading-relaxed">
          The Engineering & Delivery Officer keeps delivery visible, measured, and reuse-first —
          from request to operational capability, with the pipeline instrumented so bottlenecks
          surface instead of hiding.
        </p>
      </header>

      <DeliveryPanel />

      <LCARSPanel title="Operating model" accent="engineering" eyebrow="EDO">
        <p className="text-sm text-lcars-text/80 leading-relaxed">
          One plan approval, one closure approval — no manual orchestration in between. The Officer
          analyses, reuses first, plans, executes on a branch, validates, reports real state, updates
          Command Memory, registers capability, and surfaces the change to the XO.
        </p>
        <p className="mt-2 text-[11px] text-lcars-muted">
          See <code>governance/ENGINEERING-DELIVERY-OFFICER-CHARTER.md</code> and{' '}
          <code>Missions/MSN-EDO-001/</code>.
        </p>
      </LCARSPanel>
    </div>
  );
}
