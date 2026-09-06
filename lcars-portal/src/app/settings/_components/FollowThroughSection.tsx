'use client';

// Mission §7/§8 — persistent defaults for reminders and follow-through,
// plus a simple Telegram connection/configuration surface (never job
// logs/retry counters/scheduler internals — those are Agent & Job
// Status). intelligence/adhd/follow_through_engine.py already owns the
// real scheduling logic (capacity gating, quiet hours, daily caps); these
// are the HQ-wide defaults it and the Telegram sends can adopt —
// individual tasks may still override them, per mission §7.
import Link from 'next/link';
import { Checkbox, Select } from '@/components/ui/Input';
import { SectionHeading, SettingRow } from './SectionHeading';
import { SaveStatusLine } from './SaveStatusLine';
import { useSectionSettings } from './useSectionSettings';

export function FollowThroughSection() {
  const { value, status, save } = useSectionSettings('followThrough');

  return (
    <div>
      <SectionHeading title="Follow-through & Notifications" description="Persistent defaults for reminders and follow-through." />

      <div className="rounded-lg border border-wb-line bg-wb-surface px-4">
        <SettingRow label="Default reminder style" hint="Individual tasks may override this.">
          <Select
            aria-label="Default reminder style"
            value={value.reminderStyle}
            disabled={status === 'loading'}
            onChange={(e) => save({ ...value, reminderStyle: e.target.value as typeof value.reminderStyle })}
            className="min-w-[160px]"
          >
            <option value="once">Once</option>
            <option value="normal">Normally</option>
            <option value="persistent">Keep reminding me</option>
          </Select>
        </SettingRow>

        <SettingRow label="Increase reminders as deadlines approach">
          <Checkbox
            label=""
            aria-label="Increase reminders as deadlines approach"
            checked={value.increaseAsDeadlineApproaches}
            disabled={status === 'loading'}
            onChange={(e) => save({ ...value, increaseAsDeadlineApproaches: e.target.checked })}
          />
        </SettingRow>

        <SettingRow label="Check back when something has been waiting too long">
          <Checkbox
            label=""
            aria-label="Check back when something has been waiting too long"
            checked={value.checkBackOnWaitingItems}
            disabled={status === 'loading'}
            onChange={(e) => save({ ...value, checkBackOnWaitingItems: e.target.checked })}
          />
        </SettingRow>
      </div>

      <div className="mt-2">
        <SaveStatusLine status={status} onRetry={() => save(value)} />
      </div>

      <div className="mt-6">
        <h2 className="mb-2 text-[13px] font-semibold uppercase tracking-[0.1em] text-wb-ink2">Telegram</h2>
        <div className="rounded-lg border border-wb-line bg-wb-surface px-4">
          <SettingRow label="Follow-through messages">
            <Checkbox
              label=""
              aria-label="Follow-through messages"
              checked={value.telegram.followThroughMessages}
              disabled={status === 'loading'}
              onChange={(e) => save({ ...value, telegram: { ...value.telegram, followThroughMessages: e.target.checked } })}
            />
          </SettingRow>
          <SettingRow label="Important HQ alerts">
            <Checkbox
              label=""
              aria-label="Important HQ alerts"
              checked={value.telegram.importantAlerts}
              disabled={status === 'loading'}
              onChange={(e) => save({ ...value, telegram: { ...value.telegram, importantAlerts: e.target.checked } })}
            />
          </SettingRow>
          <SettingRow label="Weekly Review reminder">
            <Checkbox
              label=""
              aria-label="Weekly Review reminder"
              checked={value.telegram.weeklyReviewReminder}
              disabled={status === 'loading'}
              onChange={(e) => save({ ...value, telegram: { ...value.telegram, weeklyReviewReminder: e.target.checked } })}
            />
          </SettingRow>
        </div>
        <p className="mt-2 text-[12px] text-wb-ink2">
          For connection state and reconnecting Telegram, see{' '}
          <Link href="/settings/connections" className="text-wb-sage-deep hover:underline">
            Connections
          </Link>
          . For delivery health and retry logs, see{' '}
          <Link href="/agent-status-workbench" className="text-wb-sage-deep hover:underline">
            HQ Status →
          </Link>
          .
        </p>
      </div>
    </div>
  );
}
