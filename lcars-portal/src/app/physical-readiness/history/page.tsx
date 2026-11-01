import { RetiredPageNotice } from '@/components/ui/RetiredPageNotice';

// Decommissioned 2026-10-18 (owner decision).
export default function PhysicalReadinessHistoryRetired() {
  return (
    <RetiredPageNotice
      title="Physical Readiness"
      message="Physical Readiness has been retired from HQ. Its exercise catalogue now lives in Knowledge, under Exercises."
      links={[{ href: '/knowledge-workbench?tab=exercises', label: 'Go to Knowledge · Exercises' }]}
    />
  );
}
