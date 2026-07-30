import { redirect } from 'next/navigation';

// /home was the platform's original front door (see git history for the
// HomeScreen/executiveContext rationale) but was superseded by
// /workbenches as the new home (MSN-0350) — root `/` already redirects
// there. This route stayed live and full of its own dashboard content
// after the decommission, so a bookmark or old link still landed here
// instead of the new home. Redirect, matching root's behaviour, rather
// than deleting outright — /decide and /ask (the other two decommissioned
// surfaces) were fully removed, but HomeScreen/executiveContext are larger
// and still referenced elsewhere; leaving that removal for a follow-up.
export default function HomePage() {
  redirect('/workbenches');
}
