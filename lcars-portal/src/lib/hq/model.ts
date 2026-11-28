// HQ view models. HQ adds no tables and no records: every shape here is a
// read-only projection of data the existing workbenches already own.

export type HqDecisionSource =
  | 'engineering'      // build_request_inbox: traditional build request
  | 'ai-action'        // build_request_inbox: AI-proposed action (mission / decision / content)
  | 'brief'            // intelligence brief gate (QA passed -> publish)
  | 'improvement'      // HQ Evolution opportunity
  | 'knowledge'        // knowledge-library document review
  | 'intelligence';    // a decision requested on an intelligence item (HQ)

export interface HqDecision {
  /** Namespaced, stable id, e.g. "engineering:<uuid>". */
  id: string;
  source: HqDecisionSource;
  sourceLabel: string;
  title: string;
  /** What is being requested. */
  request: string;
  /** Why it matters. */
  why: string;
  /** The recommended action, in plain words. */
  recommendation: string;
  ifApprove: string;
  ifDefer: string;
  /** Whether the Captain's intervention is genuinely needed, and why. */
  need: string;
  /** True when approval can be reversed after the fact. */
  undoable: boolean;
  /** Higher = more urgent; used to order the inbox. */
  rank: number;
  /** Routine items may be grouped into one package. Never set for items
   *  that need judgement or are irreversible. */
  routine: boolean;
  /** Where this decision lives in the existing workbench, for context. */
  legacyHref: string;
  /** Options to choose between. Present only for decisions that need a choice. */
  options?: string[];
  /** Evidence carried from the source item, shown with the decision. */
  evidence?: { label: string; detail: string }[];
  /** The original intelligence item this decision is about. */
  sourceItem?: { title: string; url: string | null; hqHref: string };
  /** Opaque handle the source adapter needs to act on the item. */
  ref: unknown;
}

export interface HqPackage {
  id: string;
  title: string;
  lines: HqDecision[];
}

export type HqWorkState = 'review' | 'attention' | 'progress' | 'done';

export interface HqWorkItem {
  id: string;
  /** 'research' items are shown in their own section with a research status. */
  kind?: 'research';
  /** The status as recorded on the source (a mission status). */
  rawStatus?: string;
  title: string;
  state: HqWorkState;
  line: string;
  outputs: string[];
  /** Source system, for the "opens in existing workbench" link. */
  legacyHref: string;
  updatedAt: string | null;
}

export interface HqIntelItem {
  id: string;
  kind: string;
  lens: 'Technical' | 'Health' | 'Alerts';
  title: string;
  summary: string;
  /** Plain-language reason it matters, when the source provides one. */
  why: string | null;
  /** What the source suggests doing, when it provides one. */
  youNeedTo: string | null;
  risk: 'High' | 'Medium' | 'Low' | null;
  evidence: 'Strong' | 'Moderate' | 'Limited' | 'Unknown';
  corroboration: number | null;
  needsYou: boolean;
  watching: boolean;
  when: string | null;
  /** Original source link, when there is one. */
  url: string | null;
  sourceName: string | null;
  legacyHref: string;
}

export interface HqLibraryItem {
  id: string;
  title: string;
  type: 'Knowledge' | 'Document' | 'Intelligence' | 'Brief' | 'Content';
  /** Where the item is actually stored. HQ links to it and keeps no copy. */
  store: string;
  date: string | null;
  excerpt: string;
  legacyHref: string;
}
