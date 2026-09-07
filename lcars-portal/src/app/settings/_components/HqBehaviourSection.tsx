'use client';

// Mission §5/§6 — a small number of persistent HQ-level behaviours, not a
// per-workbench configuration exercise. defaultLandingPage draws its
// options from lib/workbenches.ts's LIVE_WORKBENCHES (the same canonical
// list the hub tile grid and workbench switcher already use — "possible
// destinations should come from existing valid routes"), and is genuinely
// applied: the login page reads it after sign-in instead of hard-coding
// /workbenches (see app/(auth)/login/page.tsx).
import { SectionHeading, SettingRow } from './SectionHeading';
import { SaveStatusLine } from './SaveStatusLine';
import { Select } from '@/components/ui/Input';
import { useSectionSettings } from './useSectionSettings';
import { LIVE_WORKBENCHES } from '@/lib/workbenches';

export function HqBehaviourSection() {
  const { value, status, save } = useSectionSettings('hqBehaviour');

  return (
    <div>
      <SectionHeading title="HQ Behaviour" description="A small number of persistent HQ-level behaviours." />
      <div className="rounded-lg border border-wb-line bg-wb-surface px-4">
        <SettingRow label="Default landing page" hint="Where HQ opens after you sign in.">
          <Select
            aria-label="Default landing page"
            value={value.defaultLandingPage}
            disabled={status === 'loading'}
            onChange={(e) => save({ ...value, defaultLandingPage: e.target.value })}
            className="min-w-[200px]"
          >
            {LIVE_WORKBENCHES.map((w) => (
              <option key={w.href} value={w.href}>
                {w.title}
              </option>
            ))}
          </Select>
        </SettingRow>

        <div className="py-4">
          <p className="text-[13px] font-medium text-wb-ink">What should HQ put in front of you?</p>
          <p className="mt-0.5 text-[12px] text-wb-ink2">
            Underlying workbenches map this to their own terms (e.g. Needs you / Worth knowing / Watching) — this is the one
            shared threshold, not a scoring formula.
          </p>
          <fieldset className="mt-3 flex flex-col gap-2">
            <legend className="sr-only">Attention preference</legend>
            <label className="flex cursor-pointer items-start gap-2 text-[13px] text-wb-ink">
              <input
                type="radio"
                name="attention-preference"
                className="mt-0.5 h-4 w-4 border-wb-line text-wb-sage-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                checked={value.attentionPreference === 'focused'}
                disabled={status === 'loading'}
                onChange={() => save({ ...value, attentionPreference: 'focused' })}
              />
              <span>
                Only things that need me or are worth knowing
                <span className="ml-1.5 text-[11px] uppercase tracking-[0.08em] text-wb-ink2">Default</span>
              </span>
            </label>
            <label className="flex cursor-pointer items-start gap-2 text-[13px] text-wb-ink">
              <input
                type="radio"
                name="attention-preference"
                className="mt-0.5 h-4 w-4 border-wb-line text-wb-sage-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                checked={value.attentionPreference === 'watching'}
                disabled={status === 'loading'}
                onChange={() => save({ ...value, attentionPreference: 'watching' })}
              />
              <span>Include things HQ is watching</span>
            </label>
          </fieldset>
        </div>
      </div>
      <div className="mt-2">
        <SaveStatusLine status={status} onRetry={() => save(value)} />
      </div>
    </div>
  );
}
