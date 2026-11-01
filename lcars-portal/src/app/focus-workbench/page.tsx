import { RetiredPageNotice } from '@/components/ui/RetiredPageNotice';

// Decommissioned 2026-10-18 (owner decision).
export default function FocusRetired() {
  return (
    <RetiredPageNotice
      title="Focus"
      message="The Focus workbench has been retired from HQ."
      links={[{ href: '/captains-chair-workbench', label: 'Go to Today' },{ href: '/ready-room', label: 'Go to Ready Room' }]}
    />
  );
}
