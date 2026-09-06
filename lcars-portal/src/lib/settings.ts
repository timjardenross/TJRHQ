// TJR HQ Settings Page Redesign mission — server-persisted preferences.
//
// A separate concern from lib/theme.ts and lib/preferences.ts (both
// localStorage, device-local, already-shipped): those stay as-is. This
// module covers the sections of Settings that need to be readable by more
// than one browser tab or by the Python intelligence pipeline (Intelligence
// monitoring preferences in particular) — so it lives server-side, in the
// user_settings table (migration 0196, renumbered from 0189), not localStorage.
//
// Single JSONB blob, single row (id='hq') — see migration 0196's comment
// for why. Every field here has a safe default; a missing/partial row
// (first run, or a section added after some Captain's row was written)
// always merges onto DEFAULT_SETTINGS rather than throwing, so a settings
// read never blocks a page render.

export interface HqBehaviourSettings {
  /** A href from lib/workbenches.ts's LIVE_WORKBENCHES — where login lands. */
  defaultLandingPage: string;
  /** Mission §6 "Attention Design Rule": the threshold for what reaches
   * normal human attention, expressed in plain terms — not a scoring
   * formula. 'focused' (default) favours attention protection; 'watching'
   * additionally surfaces monitored/lower-priority items. Workbenches and
   * the Hub's needs-attention aggregation map this to their own domain
   * semantics per mission §6 — this field is the one shared switch. */
  attentionPreference: 'focused' | 'watching';
}

export interface FollowThroughSettings {
  /** Human-facing default reminder cadence; individual tasks may override. */
  reminderStyle: 'once' | 'normal' | 'persistent';
  increaseAsDeadlineApproaches: boolean;
  checkBackOnWaitingItems: boolean;
  telegram: {
    followThroughMessages: boolean;
    importantAlerts: boolean;
    weeklyReviewReminder: boolean;
  };
}

export interface TechnicalIntelligenceSettings {
  /** Keys from config/osint_intelligence_missions.json's
   * technical.priority_categories[].key. Empty array = every category
   * enabled (the safe default) — this is an overlay of WHICH existing
   * categories to monitor, never a second copy of the category taxonomy
   * itself (that file stays the one source of truth for keys/labels/
   * keywords; see OSINT_MISSION_CONFIG_DESIGN.md). */
  enabledCategories: string[];
  geographicFocus: 'au' | 'apac' | 'global';
}

export interface HealthIntelligenceSettings {
  /** Tags from config/osint_intelligence_missions.json's
   * health.domain_tiers.*.tags[]. Empty array = every tag enabled. These
   * are monitoring-interest preferences, not diagnoses (mission §13). */
  enabledTags: string[];
}

export interface IntelligenceSettings {
  technical: TechnicalIntelligenceSettings;
  health: HealthIntelligenceSettings;
}

export interface AiAutomationSettings {
  assistanceEnabled: boolean;
  capabilities: {
    summarise: boolean;
    suggestNextActions: boolean;
    breakDownTasks: boolean;
    classifyIntelligence: boolean;
    recommendAttention: boolean;
  };
}

export interface DataPrivacySettings {
  /** A stated preference, surfaced honestly in the UI alongside what is
   * actually enforced today by core/model-router (task-type routing, not
   * a per-Captain switch yet) — see Settings' Data & Privacy section
   * copy. Not fabricated as a hard guarantee. */
  preferLocalProcessing: boolean;
}

export interface HqSettings {
  hqBehaviour: HqBehaviourSettings;
  followThrough: FollowThroughSettings;
  intelligence: IntelligenceSettings;
  aiAutomation: AiAutomationSettings;
  dataPrivacy: DataPrivacySettings;
}

export const DEFAULT_SETTINGS: HqSettings = {
  hqBehaviour: {
    defaultLandingPage: '/captains-chair-workbench',
    attentionPreference: 'focused',
  },
  followThrough: {
    reminderStyle: 'normal',
    increaseAsDeadlineApproaches: true,
    checkBackOnWaitingItems: true,
    telegram: {
      followThroughMessages: true,
      importantAlerts: true,
      weeklyReviewReminder: true,
    },
  },
  intelligence: {
    technical: {
      enabledCategories: [],
      geographicFocus: 'au',
    },
    health: {
      enabledTags: [],
    },
  },
  aiAutomation: {
    assistanceEnabled: true,
    capabilities: {
      summarise: true,
      suggestNextActions: true,
      breakDownTasks: true,
      classifyIntelligence: true,
      recommendAttention: true,
    },
  },
  dataPrivacy: {
    preferLocalProcessing: true,
  },
};

/** Deep-merges a partial/legacy row onto DEFAULT_SETTINGS so a field added
 * after some Captain's row was last written still comes back with a real
 * default instead of `undefined`. One level deep per top-level section is
 * enough — every section here is a flat-ish object, not deeply nested. */
export function mergeSettings(partial: unknown): HqSettings {
  const p = (partial && typeof partial === 'object' ? partial : {}) as Partial<HqSettings>;
  return {
    hqBehaviour: { ...DEFAULT_SETTINGS.hqBehaviour, ...p.hqBehaviour },
    followThrough: {
      ...DEFAULT_SETTINGS.followThrough,
      ...p.followThrough,
      telegram: { ...DEFAULT_SETTINGS.followThrough.telegram, ...p.followThrough?.telegram },
    },
    intelligence: {
      technical: { ...DEFAULT_SETTINGS.intelligence.technical, ...p.intelligence?.technical },
      health: { ...DEFAULT_SETTINGS.intelligence.health, ...p.intelligence?.health },
    },
    aiAutomation: {
      ...DEFAULT_SETTINGS.aiAutomation,
      ...p.aiAutomation,
      capabilities: { ...DEFAULT_SETTINGS.aiAutomation.capabilities, ...p.aiAutomation?.capabilities },
    },
    dataPrivacy: { ...DEFAULT_SETTINGS.dataPrivacy, ...p.dataPrivacy },
  };
}
