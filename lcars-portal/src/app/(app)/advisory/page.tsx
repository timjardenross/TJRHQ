// Retired — consolidated into Advisory Council (Phase 1, MSN-PORT-003).
// MSN-0328 (WP-B): was a 3-hop chain (advisory -> executive-staff ->
// chief-of-staff -> advisory-council) -- every retired page now redirects
// straight to the real destination.
import { redirect } from 'next/navigation';
export default function AdvisoryPage() {
  redirect('/advisory-council');
}
