import { getExecutiveContext } from '@/lib/executiveContext';
import { HomeScreen } from '@/components/home/HomeScreen';

// STARSHIP-REDESIGN.md §3: Home is the only landing surface now. No
// configurable start page, no redirect to a dashboard - /captains-chair
// still exists (reachable via nav) but is no longer where a session starts.
export const dynamic = 'force-dynamic';

export default async function Home() {
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
