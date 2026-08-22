import { redirect } from 'next/navigation';

// Captain's Chair's dedicated Engineering Queue sub-page was removed
// 2026-08-22 (exec-summary redesign — too detailed for that page, and the
// Captain asked for it gone outright). /engineering (legacy build-request
// inbox, read-only) is the nearest remaining live view of the same
// build_request_inbox data; it lacks the removed page's inline
// approve/reject actions.
export default function EngineeringQueuePage() {
  redirect('/engineering');
}
