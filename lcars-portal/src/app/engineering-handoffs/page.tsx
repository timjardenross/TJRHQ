import { redirect } from 'next/navigation';

// Consolidated into the Decisions page (Stage C, 2026-10-18): approved engineering handoffs are
// now the "Approved handoffs" tab beside the approvals queue. The view itself lives in
// ./_components/HandoffsView.tsx (read-only; every action opens GitHub's own review view -
// see that file's header for why). Kept as a redirect so bookmarks and links still work.
export default function EngineeringHandoffsPage() {
  redirect('/decisions?tab=handoffs');
}
