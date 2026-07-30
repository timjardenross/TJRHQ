// Shared types for the Capture Workbench.
//
// UI-only migration: the data layer stays in lib/capture.ts and the CC proxy
// at /api/capture/[id]. This file only adds the workbench's view-routing types.
// See CAPTURE-WORKBENCH-MIGRATION-PLAN.md.

/** The two work modes — one per DomainToggle tab. */
export type Domain = 'capture' | 'inbox';

export function isDomain(v: string | null): v is Domain {
  return v === 'capture' || v === 'inbox';
}

/** Per-domain eyebrow copy shown in the Shell header. */
export const EYEBROW: Record<Domain, string> = {
  capture: 'Capture it. Move on.',
  inbox: 'Triage & Route',
};

/** Inbox filter keys — ported verbatim from the legacy Capture page so the
 *  ?filter= deep-link contract (alerts, search, timeline) is preserved. */
export type InboxFilter =
  | 'all'
  | 'routed'
  | 'portal'
  | 'telegram-voice'
  | 'mission'
  | 'health'
  | 'research'
  | 'decision'
  | 'unclassified';

export const INBOX_FILTERS: { key: InboxFilter; label: string }[] = [
  { key: 'all', label: 'Pending' },
  { key: 'routed', label: 'Routed / Done' },
  { key: 'telegram-voice', label: 'Voice' },
  { key: 'mission', label: 'Mission' },
  { key: 'health', label: 'Health' },
  { key: 'research', label: 'Idea/Research' },
  { key: 'decision', label: 'Decision' },
  { key: 'unclassified', label: 'Unclassified' },
];

export function isInboxFilter(v: string | null): v is InboxFilter {
  return !!v && INBOX_FILTERS.some((f) => f.key === v);
}
