'use client';

// Mission §15-17 — simple, broad, understandable AI controls; technical
// model configuration hidden under Advanced and, per the audit, not
// actually editable anywhere in this codebase today (routing/fallback
// policy is hardcoded in core/model-router/app.py) — so Advanced links to
// the existing read-only /model-crew status page rather than fabricating
// editable "Local model" / "Fallback" fields that would silently do
// nothing.
import Link from 'next/link';
import { Checkbox } from '@/components/ui/Input';
import { SectionHeading, SettingRow } from './SectionHeading';
import { SaveStatusLine } from './SaveStatusLine';
import { useSectionSettings } from './useSectionSettings';
import type { AiAutomationSettings } from '@/lib/settings';

const CAPABILITIES: { key: keyof AiAutomationSettings['capabilities']; label: string }[] = [
  { key: 'summarise', label: 'Summarise information' },
  { key: 'suggestNextActions', label: 'Suggest next actions' },
  { key: 'breakDownTasks', label: 'Break down difficult tasks' },
  { key: 'classifyIntelligence', label: 'Classify incoming intelligence' },
  { key: 'recommendAttention', label: 'Recommend what deserves attention' },
];

export function AiAutomationSection() {
  const { value, status, save } = useSectionSettings('aiAutomation');
  const loading = status === 'loading';

  return (
    <div>
      <SectionHeading title="AI & Automation" description="How much AI assistance HQ may provide." />

      <div className="rounded-lg border border-wb-line bg-wb-surface px-4">
        <SettingRow label="AI assistance">
          <Checkbox
            label=""
            aria-label="AI assistance"
            checked={value.assistanceEnabled}
            disabled={loading}
            onChange={(e) => save({ ...value, assistanceEnabled: e.target.checked })}
          />
        </SettingRow>
      </div>

      <div className="mt-4">
        <p className="mb-2 text-[12px] text-wb-ink2">Allow HQ to:</p>
        <div className={`rounded-lg border border-wb-line bg-wb-surface p-4 ${!value.assistanceEnabled ? 'opacity-50' : ''}`}>
          <div className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
            {CAPABILITIES.map((cap) => (
              <Checkbox
                key={cap.key}
                label={cap.label}
                checked={value.capabilities[cap.key]}
                disabled={loading || !value.assistanceEnabled}
                onChange={(e) => save({ ...value, capabilities: { ...value.capabilities, [cap.key]: e.target.checked } })}
              />
            ))}
          </div>
        </div>
      </div>

      <div className="mt-2">
        <SaveStatusLine status={status} onRetry={() => save(value)} />
      </div>

      <div className="mt-6 rounded-lg border border-wb-line bg-wb-surface p-4">
        <h2 className="mb-2 text-[13px] font-semibold uppercase tracking-[0.08em] text-wb-ink2">HQ will ask before:</h2>
        <ul className="list-disc space-y-1 pl-5 text-[13px] text-wb-ink">
          <li>publishing content</li>
          <li>creating a Mission</li>
          <li>making consequential evidence/curation decisions where human review is required</li>
          <li>closing important work where confirmation is expected</li>
        </ul>
        <p className="mt-3 text-[12px] text-wb-ink2">
          Background classification and everyday suggestions don&apos;t require confirmation — AI proposes, and you decide
          where it materially matters.
        </p>
      </div>

      <details className="mt-6 rounded-lg border border-wb-line bg-wb-surface p-4">
        <summary className="cursor-pointer text-[13px] font-medium text-wb-ink">Advanced</summary>
        <div className="mt-3 text-[13px] text-wb-ink2">
          <p>
            Model routing, local-vs-cloud fallback, and model health are managed automatically and shown read-only in{' '}
            <Link href="/model-crew" className="text-wb-sage-deep hover:underline">
              Model Crew
            </Link>
            . There&apos;s no per-Captain model selection to configure here today.
          </p>
        </div>
      </details>
    </div>
  );
}
