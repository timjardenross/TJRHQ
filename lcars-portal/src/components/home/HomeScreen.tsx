'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import type { VerificationResult, VerificationState } from '@/lib/verification';
import { homeCopyFor, fmtTime, needsYouText, type NeedsYouState } from '@/lib/homeCopy';
import { fetchDecideCount } from '@/lib/decide';
import type { SessionBoundary } from '@/lib/homeSessions';

// STARSHIP-REDESIGN.md §3. Four blocks, one screen, no persistent nav.
// MSN-0349: "Since yesterday" and "Worth knowing" are now powered by the
// Executive Change and Interrupt Assemblies (executiveContext.ts, computed
// server-side in page.tsx) rather than static placeholder copy.

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
    <main className="min-h-screen flex justify-center bg-[#0B1017] text-[#E8EDF2]">
      <div className="w-full max-w-[620px] px-7 pt-12 pb-14 sm:pt-16 flex flex-col min-h-screen">

        {/* 1 · Am I okay? */}
        <div className="mb-10 sm:mb-16">
          <p className="text-sm uppercase tracking-[0.14em] text-[#5A6875] mb-6 font-medium">
            {daypart}
          </p>
          <h1
            className="text-[30px] sm:text-[40px] leading-[1.18] mb-6"
            style={{
              // The app's globals.css forces all h1/h2/h3 to uppercase
              // sans-serif (@layer base) for the existing LCARS design
              // system - Home is deliberately breaking from that (spec §7:
              // serif display for the human voice), so these are pinned
              // inline rather than fought via the Tailwind utility cascade.
              fontFamily: '"New York", "SF Pro Display", Georgia, serif',
              fontWeight: 500,
              textTransform: 'none',
              letterSpacing: '-0.015em',
            }}
          >
            {copy.headline}
          </h1>
          <div className="flex items-center gap-3 text-[#93A1B0] text-[15.5px]">
            <VerificationRing color={copy.ringColor} />
            <span>{copy.verifyText}</span>
            {copy.showVerifiedTime && verifiedTime && (
              <>
                <span className="text-[#5A6875]">·</span>
                <span className="tabular-nums text-[#93A1B0]">verified {verifiedTime}</span>
              </>
            )}
          </div>
          {copy.coverage && (
            <p className="mt-2 pl-[24px] text-[13px] tabular-nums text-[#5A6875]">
              {copy.coverage}
            </p>
          )}
        </div>

        {/* 2 · Needs you */}
        <Section eyebrow="Needs you" ringColor={copy.ringColor}>
          {needsYou.status === 'ok' && needsYou.count > 0 ? (
            <Link
              href="/decide"
              className="text-[19px] font-normal text-[#E8EDF2] leading-relaxed underline underline-offset-4 decoration-[rgba(147,161,176,0.4)] hover:decoration-[#E8EDF2]"
            >
              {needsYouText(needsYou)}
            </Link>
          ) : (
            <p className="text-[19px] font-normal text-[#E8EDF2] leading-relaxed">
              {needsYouText(needsYou)}
            </p>
          )}
        </Section>

        {/* 3 · Since yesterday */}
        <Section eyebrow={changeEyebrow(session)} ringColor={copy.ringColor}>
          <p className="text-[16.5px] text-[#93A1B0] leading-relaxed">
            {changeText}
          </p>
        </Section>

        {/* 4 · Worth knowing */}
        <Section eyebrow="Worth knowing" ringColor={copy.ringColor}>
          <p
            className="text-[20px] leading-relaxed px-6 py-5 rounded-md border border-[rgba(147,161,176,0.14)]"
            style={{
              fontFamily: '"New York", "SF Pro Display", Georgia, serif',
              fontWeight: 450,
              color: '#E8EDF2',
              background: '#101722',
              borderLeft: `3px solid ${copy.ringColor}`,
            }}
          >
            {worthKnowingText}
            {primaryInterrupt && (
              <span className="block mt-2 text-[13px] font-sans text-[#5A6875]">
                {primaryInterrupt.domain}
              </span>
            )}
          </p>
        </Section>

        <div className="mt-auto pt-14 flex items-center justify-between gap-3">
          <footer className="text-[12.5px] text-[#5A6875] flex items-center gap-2">
            <span
              className="w-[5px] h-[5px] rounded-full inline-block"
              style={{ background: copy.ringColor, opacity: 0.6 }}
            />
            Verified by Starship · Last checked {verifiedTime ?? 'never'}
          </footer>
          {/* STARSHIP-REDESIGN.md §7/§2: Ask is always reachable, quietly -
              no persistent nav bar, just this one small affordance. */}
          <Link href="/ask" className="text-[12.5px] text-[#5A6875] hover:text-[#93A1B0] underline underline-offset-2">
            Ask
          </Link>
        </div>
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
    <section
      className="py-7"
      style={{ borderTop: '1px solid rgba(147,161,176,0.14)' }}
      aria-label={eyebrow}
    >
      <p className="text-xs uppercase tracking-[0.16em] text-[#5A6875] font-semibold mb-4 flex items-center">
        <span
          className="inline-block w-[18px] h-[3px] rounded-sm mr-2.5"
          style={{ background: ringColor, opacity: 0.55 }}
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
