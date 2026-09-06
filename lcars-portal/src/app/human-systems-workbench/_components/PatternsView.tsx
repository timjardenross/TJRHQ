'use client';

// PATTERNS tab — placeholder shell for the Human Systems redesign
// (2026-09-06 Phase 2). Currently just the existing System Learning
// collapsible (possible-pattern narrative, worth-testing/what-changed
// experiment layers) plus a note on what's coming. A follow-up mission
// (spec sections 22-24) will flesh this out into a real patterns view —
// this pass's job was only to get the nav shell + correct content routing
// in place without regressing anything.

import { SystemLearningSection } from './RecoveryView';
import type { RecoveryPayload } from './types';

export function PatternsView({ recovery }: { recovery: RecoveryPayload }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <SystemLearningSection data={recovery} className="md:col-span-2" />
      <p className="text-[12px] text-wb-ink2 md:col-span-2">
        More pattern detail (recurring loads, redesign candidates, longer-run correlations) is planned for this tab.
      </p>
    </div>
  );
}
