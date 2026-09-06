'use client';

// Mission §18/§28 — understandable controls only, and never a control that
// looks live but does nothing. The audit (Phase 0) found no data-export,
// clear-data, or history-viewer capability anywhere in this codebase
// today, so those render as clearly-labelled "Coming soon" — the same
// honest-placeholder convention Sidebar.tsx already uses for Help — rather
// than wired-looking buttons that silently no-op. Only "Prefer local
// processing" is a real, persisted preference; its copy says exactly what
// it is (a stated preference) rather than overclaiming full enforcement.
import Link from 'next/link';
import { Checkbox } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { SectionHeading, SettingRow } from './SectionHeading';
import { SaveStatusLine } from './SaveStatusLine';
import { useSectionSettings } from './useSectionSettings';

function ComingSoonRow({ label, description }: { label: string; description: string }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-wb-line py-4 last:border-b-0">
      <div className="min-w-0 flex-1 pr-4">
        <p className="text-[13px] font-medium text-wb-ink">
          {label} <span className="ml-1 text-[10px] uppercase tracking-[0.1em] text-wb-ink2">Soon</span>
        </p>
        <p className="mt-0.5 text-[12px] text-wb-ink2">{description}</p>
      </div>
      <Button variant="secondary" size="sm" disabled>
        {label}
      </Button>
    </div>
  );
}

export function DataPrivacySection() {
  const { value, status, save } = useSectionSettings('dataPrivacy');

  return (
    <div>
      <SectionHeading title="Data & Privacy" description="Understandable control over your HQ data." />

      <div className="rounded-lg border border-wb-line bg-wb-surface px-4">
        <ComingSoonRow label="Export my data" description="A full export of your HQ data, in one file." />
        <ComingSoonRow label="Manage history" description="Review and manage your activity history across HQ." />
      </div>

      <div className="mt-6 rounded-lg border border-wb-line bg-wb-surface px-4">
        <SettingRow
          label="Prefer local processing"
          hint="A stated preference. Some tasks still route to a cloud model automatically when a local model can't handle them — see Model Crew."
        >
          <Checkbox
            label=""
            aria-label="Prefer local processing"
            checked={value.preferLocalProcessing}
            disabled={status === 'loading'}
            onChange={(e) => save({ ...value, preferLocalProcessing: e.target.checked })}
          />
        </SettingRow>
      </div>
      <p className="mt-2 text-[12px] text-wb-ink2">
        <Link href="/model-crew" className="text-wb-sage-deep hover:underline">
          View current model routing →
        </Link>
      </p>
      <div className="mt-2">
        <SaveStatusLine status={status} onRetry={() => save(value)} />
      </div>

      <div className="mt-6 rounded-lg border border-wb-crit bg-wb-surface px-4">
        <h2 className="border-b border-wb-line py-3 text-[12px] font-semibold uppercase tracking-[0.1em] text-wb-crit-on">
          Danger Zone
        </h2>
        <ComingSoonRow label="Clear specific HQ data…" description="Delete a specific category of HQ data. Not available yet." />
      </div>
    </div>
  );
}
