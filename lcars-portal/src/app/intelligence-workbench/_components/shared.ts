// Shared types/constants for the Today/Watching/Library briefing views
// (Technical OSINT Three-Workbench Simplification Phase 1).
//
// Terminology mapping applied throughout (mission spec §6):
//   ESCALATE  -> "Needs you"
//   BRIEF     -> "Worth knowing"
//   WATCH     -> "Watching"
//   REFERENCE -> "Library / Background"
//   SUPPRESS  -> "Hidden"
//   Known Unknowns    -> "What we don't know yet"
//   Signal            -> "Development"
//   Threat Assessment -> "Assessment / What matters"
//   Corroboration     -> "Sources / Supporting evidence"

export type Disposition = 'ESCALATE' | 'BRIEF' | 'WATCH' | 'REFERENCE' | 'SUPPRESS';

export const DISPOSITION_LABEL: Record<Disposition, string> = {
  ESCALATE: 'Needs you',
  BRIEF: 'Worth knowing',
  WATCH: 'Watching',
  REFERENCE: 'Library / Background',
  SUPPRESS: 'Hidden',
};

export interface Development {
  event_id: string;
  title: string;
  canonical_url: string | null;
  what_happened: string;
  why_you_care: string;
  assessment: string;
  you_need_to: string;
  confidence_level: string;
  corroboration: number;
  published_at: string | null;
}

/** Static known-unknowns statement — the same content the pre-existing
 * intelligence-summary route already returned (not invented for this
 * uplift), used as a fallback if /api/intelligence-workbench/today ever
 * returns an empty unknowns array. There is no backend field yet for a
 * dynamically-computed gap statement. */
export const KNOWN_UNKNOWNS = [
  { title: 'Internal network security', impact: 'Blind to internal compromise', need: 'SIEM integration' },
  { title: 'Supply chain threats', impact: 'Third-party compromise', need: 'Vendor monitoring' },
  { title: 'Zero-day activity', impact: 'Unpatched vulnerabilities in use', need: 'EDR, threat hunting' },
];
