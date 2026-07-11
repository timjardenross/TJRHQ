// Canonical Architecture Decisions §1 (docs/EOS-CANONICAL-ARCHITECTURE-DECISIONS.md):
// HomeScreen becomes the platform's real front door. This route was
// created because none previously existed - HomeScreen.tsx and
// executiveContext.ts (MSN-0349-0354) were built, tested, and documented
// but never mounted; the Home nav link pointed at /captains-chair, a
// different, older dashboard. Lives outside the (app) route group
// deliberately, matching /decide and /ask - the (app) group's layout adds
// LCARS nav chrome; Home, Decide and Ask are the three surfaces with zero
// persistent nav by design (STARSHIP-REDESIGN.md §2/§7).
//
// Server Component: getExecutiveContext() composes verification + Change
// Assembly + Interrupt Assembly server-side, once, into the one state
// HomeScreen (a Client Component) renders - no duplicate truth, no second
// parallel status system, per executiveContext.ts's own header comment.

import { getExecutiveContext } from '@/lib/executiveContext';
import { HomeScreen } from '@/components/home/HomeScreen';

export default async function HomePage() {
  const ctx = await getExecutiveContext();

  return (
    <HomeScreen
      verification={ctx.verification}
      composedState={ctx.state}
      session={ctx.session}
      changeText={ctx.changeText}
      primaryInterrupt={ctx.primaryInterrupt}
      interruptsComplete={ctx.interrupts.complete}
    />
  );
}
