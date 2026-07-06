// Retired — consolidated into Advisory Council (Phase 1, MSN-PORT-003).
// MSN-0328 (WP-B): collapsed the 3-hop redirect chain — see advisory/page.tsx.
import { redirect } from 'next/navigation';
export default function ExecutiveStaffPage() {
  redirect('/advisory-council');
}
