import { redirect } from 'next/navigation';

// The Library domain (and the Memory|Library toggle this ?domain= param
// used to select) was pulled back to draft 2026-08-22 (see
// knowledge-workbench/page.tsx's own comment) — the workbench page never
// reads this param and unconditionally renders Memory. Redirecting here
// with ?domain=library therefore silently served Memory to anyone
// following this link with zero indication their intended destination
// doesn't exist yet. Plain redirect until Library returns.
export default function KnowledgeLibraryPage() {
  redirect('/knowledge-workbench');
}
