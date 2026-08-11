'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import type { VerificationResult, VerificationState } from '@/lib/verification';
import { homeCopyFor, fmtTime, needsYouText, type NeedsYouState } from '@/lib/homeCopy';
import { fetchDecideCount } from '@/lib/decide';
import { investigationTypeForDomain } from '@/lib/investigate';
import type { SessionBoundary } from '@/lib/homeSessions';

// STARSHIP-REDESIGN.md §3. Four blocks, one screen, no persistent nav.
// MSN-0349: "Since yesterday" and "Worth knowing" are now powered by the
// Executive Change and Interrupt Assemblies (executiveContext.ts, computed
// server-side in page.tsx) rather than static placeholder copy.
//
// Real-Captain-walkthrough revision (2026-07-10): two pieces of direct
// feedback after actually using this page, not a compile check. (1) "Hate
// the black" - this page used a bespoke near-black (#0B1017) palette found
// nowhere else in the platform, unrelated to either the LCARS design system
// or the real public brand. (2) "No way to direct things" - resolved as
// "keep zero-nav, but make Home a real hub": every real experience now gets
// a findable link here, not just the ones tied to an active interrupt.
// Visual language now reuses the actual public-site brand
// (components/public/PublicShell.tsx - the real tjrmindbody.com tokens:
// #f5f7fb background, #172033/#18223a navy text, #243b7a accent, soft
// rounded cards) instead of a third, one-off palette. All data/logic below
// is unchanged - verification, decide count, change assembly, interrupt
// assembly all work exactly as before; this is a visual + information-
// architecture change only.

export interface PrimaryInterrupt {
  domain: string;
  text: string;
  evidenceAt: string;
}

/** MSN-0349 Objective 5: returning-after-absence must be first-class, not
 * a special case bolted on - this is the one place that decides how the
 * "since X" eyebrow adapts to how long it's actually been. */
function changeEyebrow(session: SessionBoundary): string {
  if (session.daysSinceLastSession === null) return 'Getting started';
  if (session.daysSinceLastSession === 0) return 'Since earlier today';
  if (session.daysSinceLastSession === 1) return 'Since yesterday';
  return `Since your last visit — ${session.daysSinceLastSession} days ago`;
}

/** Every real experience the Captain can reach, grouped for the Explore
 * hub below. Investigate is deliberately excluded - it requires a real
 * ?type=&reason= a specific journey already knows (its own page says so:
 * "reach this from a link on Home or Recommended") - a blind link here
 * would just be a dead end, not a genuine entry point. */
const EXPLORE_LINKS: { href: string; label: string; description: string }[] = [  { href: '/advisory-workbench', label: 'Advisory Council', description: "Consult the ship's officers, evidence-backed" },  { href: '/human-systems', label: 'Human Systems', description: 'Capacity, recovery, and today’s highest-leverage action' },
  { href: '/missions', label: 'Missions', description: 'The full mission registry' },
  { href: '/captains-brief-workbench', label: "Captain's Brief", description: 'The composed intelligence document' },
  { href: '/content-workbench', label: 'Communications Pipeline', description: 'Review, edit, and publish drafted communications' },
  { href: '/captains-chair', label: "Captain's Chair", description: 'The full operational dashboard' },
];

export function HomeScreen({
  verification,
  composedState,
  session,
  changeText,
  primaryInterrupt,
  interruptsComplete,
}: {
  verification: VerificationResult;
  composedState: VerificationState;
  session: SessionBoundary;
  changeText: string;
  primaryInterrupt: PrimaryInterrupt | null;
  interruptsComplete: boolean;
}) {
  const [daypart, setDaypart] = useState('Hello');
  const [needsYou, setNeedsYou] = useState<NeedsYouState>({ status: 'loading' });

  useEffect(() => {
    const h = new Date().getHours();
    setDaypart(h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening');
  }, []);

  useEffect(() => {
    fetchDecideCount()
      .then((count) => setNeedsYou({ status: 'ok', count }))
      .catch(() => setNeedsYou({ status: 'error' }));
  }, []);

  const copy = homeCopyFor(verification, composedState);
  const verifiedTime = fmtTime(verification.last_verified_at);

  const worthKnowingText = primaryInterrupt
    ? primaryInterrupt.text
    : interruptsComplete
      ? "Nothing stood out as worth flagging right now."
      : "I couldn't check every source for something worth flagging just now.";

  return (
    <main className="min-h-screen bg-[#f5f7fb] text-[#172033]">
      <div className="mx-auto w-full max-w-[720px] px-5 py-10 sm:px-8 sm:py-14 flex flex-col min-h-screen">

        {/* 1 · Am I okay? */}
        <div className="mb-8 sm:mb-10 rounded-[28px] border border-[#d9e1f0] bg-white/92 px-6 py-7 sm:px-8 sm:py-8 shadow-[0_20px_60px_rgba(23,32,51,0.06)]">
          <p className="text-sm uppercase tracking-[0.14em] text-[#61718c] mb-4 font-medium">
            {daypart}
          </p>
          <h1 className="text-[28px] sm:text-[36px] leading-[1.2] font-semibold tracking-[-0.02em] text-[#18223a] mb-5">
            {copy.headline}
          </h1>
          <div className="flex items-center gap-3 text-[#4d5d77] text-[15px]">
            <VerificationRing color={copy.ringColor} />
            <span>{copy.verifyText}</span>
            {copy.showVerifiedTime && verifiedTime && (
              <>
                <span className="text-[#a0abc2]">·</span>
                <span className="tabular-nums text-[#4d5d77]">verified {verifiedTime}</span>
              </>
            )}
          </div>
          {copy.coverage && (
            <p className="mt-2 pl-[24px] text-[13px] tabular-nums text-[#61718c]">
              {copy.coverage}
            </p>
          )}
        </div>

        {/* 2 · Needs you */}
        <Section eyebrow="Needs you" ringColor={copy.ringColor}>
          {needsYou.status === 'ok' && needsYou.count > 0 ? (
            <Link
              href="/workbenches"
              className="text-[18px] font-normal text-[#18223a] leading-relaxed underline underline-offset-4 decoration-[#c3cee3] hover:decoration-[#243b7a]"
            >
              {needsYouText(needsYou)}
            </Link>
          ) : (
            <p className="text-[18px] font-normal text-[#18223a] leading-relaxed">
              {needsYouText(needsYou)}
            </p>
          )}
        </Section>

        {/* 3 · Since yesterday */}
        <Section eyebrow={changeEyebrow(session)} ringColor={copy.ringColor}>
          <p className="text-[15.5px] text-[#4d5d77] leading-relaxed">
            {changeText}
          </p>
        </Section>

        {/* 4 · Worth knowing */}
        <Section eyebrow="Worth knowing" ringColor={copy.ringColor}>
          <p
            className="text-[17px] leading-relaxed px-6 py-5 rounded-2xl border border-[#d9e1f0] bg-white/92 text-[#18223a]"
            style={{ borderLeft: `3px solid ${copy.ringColor}` }}
          >
            {worthKnowingText}
            {primaryInterrupt && (
              <span className="block mt-2 text-[13px] text-[#61718c]">
                {primaryInterrupt.domain}
              </span>
            )}
          </p>
          {/* EOS Phase 2 Priority 2 (Executive Intelligence): composes the
              existing Attention Engine output above with the two other
              real, already-built capabilities - Captain Intelligence
              (/captains-brief, already composes Event Bus + Attention +
              Priority into one document, reused as-is) and the
              Investigation Engine (MSN-0357, reused via /investigate).
              Both links are contextual, appearing only when there's real
              evidence to follow - no standing menu, matching MSN-0353. */}
          {primaryInterrupt && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 pl-1">
              <Link
                href="/captains-brief-workbench"
                className="text-[12.5px] text-[#61718c] hover:text-[#243b7a] underline underline-offset-2"
              >
                See the full picture
              </Link>
              {investigationTypeForDomain(primaryInterrupt.domain) && (
                <Link
                  href={`/investigate?type=${encodeURIComponent(investigationTypeForDomain(primaryInterrupt.domain)!)}&reason=${encodeURIComponent(primaryInterrupt.text)}`}
                  className="text-[12.5px] text-[#61718c] hover:text-[#243b7a] underline underline-offset-2"
                >
                  Investigate
                </Link>
              )}
            </div>
          )}
        </Section>

        {/* 5 · Explore - the real hub. Every experience, always findable,
            not gated behind an interrupt deciding it's relevant. Still no
            persistent nav bar - this is one section on one page, reached
            by scrolling Home, not a menu that follows you everywhere. */}
        <Section eyebrow="Explore" ringColor={copy.ringColor}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {EXPLORE_LINKS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="group rounded-2xl border border-[#d9e1f0] bg-white/92 px-4 py-3.5 transition hover:border-[#243b7a] hover:shadow-[0_8px_24px_rgba(23,32,51,0.08)]"
              >
                <p className="text-[15px] font-semibold text-[#18223a] group-hover:text-[#243b7a]">
                  {item.label}
                </p>
                <p className="mt-0.5 text-[13px] text-[#61718c] leading-snug">
                  {item.description}
                </p>
              </Link>
            ))}
          </div>
        </Section>

        <footer className="mt-10 pt-6 border-t border-[#d9e1f0] text-[12.5px] text-[#61718c] flex items-center gap-2">
          <span
            className="w-[5px] h-[5px] rounded-full inline-block"
            style={{ background: copy.ringColor, opacity: 0.7 }}
          />
          Verified by Starship · Last checked {verifiedTime ?? 'never'}
        </footer>
      </div>
    </main>
  );
}

function Section({
  eyebrow,
  ringColor,
  children,
}: {
  eyebrow: string;
  ringColor: string;
  children: React.ReactNode;
}) {
  return (
    <section className="py-6" aria-label={eyebrow}>
      <p className="text-xs uppercase tracking-[0.16em] text-[#61718c] font-semibold mb-3.5 flex items-center">
        <span
          className="inline-block w-[18px] h-[3px] rounded-sm mr-2.5"
          style={{ background: ringColor, opacity: 0.7 }}
        />
        {eyebrow}
      </p>
      {children}
    </section>
  );
}

function VerificationRing({ color }: { color: string }) {
  return (
    <span
      role="img"
      aria-label="Verification status"
      className="relative inline-block w-3 h-3 rounded-full shrink-0 starship-ring"
      style={{ background: color, boxShadow: `0 0 14px ${color}73` }}
    >
      <style jsx>{`
        .starship-ring::before {
          content: '';
          position: absolute;
          inset: -7px;
          border-radius: 9999px;
          border: 1px solid ${color};
          opacity: 0.3;
          animation: starship-breathe 5s ease-in-out infinite;
        }
        @keyframes starship-breathe {
          0%,
          100% {
            transform: scale(0.8);
            opacity: 0.18;
          }
          50% {
            transform: scale(1.25);
            opacity: 0.45;
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .starship-ring::before {
            animation: none;
            opacity: 0.3;
          }
        }
      `}</style>
    </span>
  );
}
