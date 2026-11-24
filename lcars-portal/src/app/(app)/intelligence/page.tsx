import Link from 'next/link';
import { productHref, intelligenceTabHref, INCIDENTS_TAB, SOURCES_TAB, INTELLIGENCE_HOME_PATH } from '@/lib/intelligenceLinks';

// Retired pointer (Mission 7 legacy-page sweep, §35; consolidated 2026-11-24). The Intelligence experience lives in ONE place,
// /intelligence-workbench (Today / Watching / Library / Incidents / Products / Source coverage). This page holds no content of its own:
// it only links to the workbench tabs so an old bookmark lands somewhere real. Other successors of the retired six tabs:
// Latest Brief / Daily Briefs / ORI Archive -> /briefs; Content -> /content-workbench.
export default function IntelligencePage() {
  const link = 'text-wb-sage-deep underline hover:no-underline';
  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-sans text-lg font-bold uppercase tracking-wider text-wb-ink">Intelligence</h1>
      <p className="mt-3 text-wb-body leading-relaxed text-wb-ink2">This page moved. Intelligence now lives in the Technical OSINT Workbench.</p>
      <ul className="mt-4 space-y-2 text-wb-body text-wb-ink2">
        <li>
          Incidents (clustered, by tier):{' '}
          <Link href={intelligenceTabHref(INCIDENTS_TAB)} className={link}>Go to Incidents →</Link>
        </li>
        <li>
          Intelligence products:{' '}
          <Link href={productHref()} className={link}>Go to Products →</Link>
        </li>
        <li>
          Source coverage:{' '}
          <Link href={intelligenceTabHref(SOURCES_TAB)} className={link}>Go to Source coverage →</Link>
        </li>
        <li>
          Signals, Themes:{' '}
          <Link href={INTELLIGENCE_HOME_PATH} className={link}>Go to Technical OSINT Workbench →</Link>
        </li>
        <li>
          Latest Brief, Daily Briefs, ORI Archive:{' '}
          <Link href="/briefs" className={link}>Go to Briefs →</Link>
        </li>
        <li>
          Content:{' '}
          <Link href="/content-workbench" className={link}>Go to Content Workbench →</Link>
        </li>
      </ul>
    </div>
  );
}
