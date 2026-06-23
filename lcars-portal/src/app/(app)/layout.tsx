import { LCARSHeader } from '@/components/LCARSHeader';
import { LCARSNav } from '@/components/LCARSNav';
import { LCARSBottomNav } from '@/components/LCARSBottomNav';
import { MobileCommandBar } from '@/components/MobileCommandBar';
import { SignOutButton } from '@/components/SignOutButton';
import { SHIP } from '@/lib/mockData';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col px-3 py-3 pb-24 md:px-5 md:py-5 lg:pb-5">
      <LCARSHeader
        ship={SHIP.name}
        registry={SHIP.registry}
        stardate={SHIP.stardate}
        pageTitle="USS TJR — Starship Endeavour"
      />
      <div className="mt-4 flex flex-1 flex-col gap-4 lg:flex-row">
        <LCARSNav />
        <main className="flex-1">{children}</main>
      </div>
      <LCARSBottomNav />
      <MobileCommandBar />
      <footer className="mt-4 flex flex-col items-start justify-between gap-2 border-t border-edge pt-4 text-xs text-lcars-muted md:flex-row md:items-center">
        <span>
          {SHIP.name} · {SHIP.registry}
        </span>
        <div className="flex items-center gap-4">
          <span className="uppercase tracking-[0.2em]">
            LCARS Portal · ROS-001 v1.1
          </span>
          <SignOutButton />
        </div>
      </footer>
    </div>
  );
}
