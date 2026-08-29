/**
 * Shared types for the LCARS portal.
 *
 * Where a type maps onto an existing Command Centre backend response, the
 * source endpoint is noted so Phase 2 can map live data onto the same shape
 * (see core/command-centre/backend/api/*). Phase 1 fills these with mock data.
 */

export type DepartmentKey =
  | 'command'
  | 'engineering'
  | 'operations'
  | 'medical'
  | 'science'
  | 'status';

export type StatusTone =
  | 'command'
  | 'engineering'
  | 'operations'
  | 'medical'
  | 'science'
  | 'status'
  | 'neutral';

/**
 * Operational state tone — independent of department identity colour
 * (MSN-0315 Phase 1A). Use this for anything communicating live/health/
 * confidence/escalation state; use `StatusTone` only for department
 * identity. See `stateToneClasses` in `./departments`.
 *
 * `info` added 2026-08-29 (docs/Severity-Vocab-Canonicalization-Plan-
 * 2026-08-29.md) — a genuine "benign/FYI" state distinct from `unknown`
 * ("we don't know"). Merged in from Badge's independent status vocabulary
 * as part of collapsing every severity vocabulary onto this one enum.
 */
export type StateTone = 'ok' | 'warn' | 'crit' | 'unknown' | 'info';

/** Mirrors mission-registry-reader.js mission rows and Supabase missions table. */
export interface Mission {
  mission_id: string;
  title: string;
  priority: 'P0' | 'P1' | 'P2' | 'P3' | '—';
  status: string;
  // Mock-only fields (not in DB)
  owner?: string;
  specialist?: string;
  reference?: string;
  department?: DepartmentKey;
  // DB fields
  id?: string;
  description?: string;
  task_type?: string;
  mission_type?: string;
  repo?: string;
  branch_name?: string;
  pr_url?: string;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
  outcome_rating?: number | null;
  closed_at?: string | null;
  rework_of?: string | null;
}

/** Mirrors GET /api/v1/missions/summary. */
export interface MissionSummary {
  total: number;
  active: number;
  in_progress: number;
  completed: number;
  blocked: number;
  by_priority: { P0: number; P1: number; P2: number; P3: number };
  timestamp: string;
}

export interface Department {
  key: DepartmentKey;
  name: string;
  lead: string;
  status: string;
  tone: StatusTone;
  summary: string;
  metrics: { label: string; value: string }[];
}

export interface Alert {
  id: string;
  level: 'critical' | 'warning' | 'info' | 'nominal';
  title: string;
  detail: string;
  source: string;
  timestamp: string;
}

/** Mirrors GET /api/v1/context/captain-brief (subset). */
export interface CaptainBrief {
  stardate: string;
  greeting: string;
  headline: string;
  priorities: string[];
  posture: { label: string; value: string; tone: StatusTone }[];
}

/** Mirrors GET /api/v1/context/operating-picture (subset). */
export interface OperatingPicture {
  readiness: string;
  activeMissions: number;
  blockers: number;
  crewOnDuty: number;
}

export interface CrewMember {
  id: string;
  name: string;
  role: string;
  department: DepartmentKey;
  status: string;
  tone: StatusTone;
  focus: string;
}

/** Mirrors GET /api/v1/personal-health / context/health (subset). */
export interface WellnessMetric {
  label: string;
  value: string;
  trend: 'up' | 'down' | 'steady';
  tone: StatusTone;
}

/** Mirrors GET /api/v1/health/services (subset). */
export interface ServiceStatus {
  name: string;
  state: 'operational' | 'degraded' | 'offline';
  detail: string;
  tone: StatusTone;
}

/** Mirrors GET /api/v1/intelligence/latest (subset) — drives the XO Brief. */
export interface BriefSection {
  heading: string;
  body: string;
}

export interface IntelligenceBrief {
  id: string;
  title: string;
  generated: string;
  summary: string;
  sections: BriefSection[];
  themes: string[];
}

export interface KnowledgeArticle {
  id: string;
  title: string;
  category: string;
  owner: string;
  updated: string;
  excerpt: string;
  department: DepartmentKey;
}

/** Ship system health bar (0–100). */
export interface ShipSystemStatus {
  label: string;
  value: number;
}

/** Captain's daily schedule entry. */
export interface TimelineEvent {
  time: string;
  title: string;
  status: 'completed' | 'in_progress' | 'scheduled';
}

/** Decision item awaiting captain approval. */
export interface DecisionItem {
  id: string;
  title: string;
  detail: string;
  from: string;
}

/** Single column in the mission Kanban board. */
export interface MissionBoardColumn {
  label: string;
  count: number;
  tone: DepartmentKey;
  items: { title: string; meta: string }[];
}

/** Single row in Today's Briefing / summary panels. */
export interface BriefingItem {
  label: string;
  value: string;
  tone: StatusTone;
}

/** Engineering / ops queue summary row. */
export interface QueueItem {
  label: string;
  count: number;
  tone: StatusTone;
}

/** Research queue item (Astrometrics / XO Brief). */
export interface ResearchQueueItem {
  id: string;
  title: string;
  location: string;
  status: 'in_progress' | 'queued' | 'completed';
  tone: StatusTone;
}

/** Crew headcount per department (Number One / XO Command). */
export interface DeptCrewCount {
  key: DepartmentKey;
  count: number;
  status: StatusTone;
}

/** Latest discovery highlight (Astrometrics). */
export interface LatestDiscovery {
  designation: string;
  classification: string;
  distance: string;
  detail: string;
}

// ── ROS-001 v1.1 — Recovery Operating System types ────────────────────────────

export type RecoveryPostureBand = 'STRONG' | 'STABLE' | 'FRAGILE' | 'REST' | 'UNKNOWN';
export type CapacityBand = 'GOOD' | 'MODERATE' | 'LIMITED' | 'REST' | 'UNKNOWN';
export type NervousSystemState = 'calm' | 'activated' | 'dysregulated';

/** Operational recovery posture — from get_recovery_posture(). */
export interface RecoveryPosture {
  posture: RecoveryPostureBand;
  posture_message: string;
  capacity_band: CapacityBand;
  capacity_message: string;
  best_window: string;
  mission_guidance: string;
  data_available: boolean;
}

/** Today's body context signals — from analytics_health_daily. */
export interface BodyContext {
  sleep_hours: number;
  sleep_quality: 'Good' | 'Fair' | 'Poor';
  cpap_compliant: boolean;
  nervous_system_state: NervousSystemState;
  energy: 'High' | 'Moderate' | 'Low';
  body_signals: 'Low' | 'Moderate' | 'High';
  sitting_window_minutes: number;
}

/** Mission load guidance derived from recovery posture. */
export interface MissionLoadGuidanceData {
  posture: RecoveryPostureBand;
  active_mission_id: string;
  active_mission_safe: boolean;
  new_starts_recommended: boolean;
  decisions_pending: number;
  defer_decisions: boolean;
}

/** One of the four recovery indexes displayed in Medical Bay. */
export interface RecoveryIndex {
  key: 'sleep' | 'nervous_system' | 'energy' | 'capacity';
  label: string;
  band: 'good' | 'moderate' | 'limited' | 'rest' | 'unknown';
  detail: string;
  tone: StatusTone;
}

/** Life Participation score and its five component signals. */
export interface LifeParticipationScore {
  score: number; // 0–100
  band: 'good' | 'moderate' | 'limited' | 'rest';
  movement_done: boolean;
  pleasure_marker: string | null;
  social_noted: boolean;
  sitting_minutes: number;
  sitting_baseline_minutes: number;
  workload_constraint: 'none' | 'light' | 'moderate' | 'severe' | 'unknown';
}

/** A single data point for the PosturePatternChart (last N days). */
export interface PostureDataPoint {
  date: string; // ISO YYYY-MM-DD
  posture: RecoveryPostureBand;
  score: number | null; // Medical Officer only — not displayed to Captain
}

/** Recent posture history for the Medical Bay pattern chart. */
export interface PostureHistory {
  days: PostureDataPoint[];
  period_label: string; // e.g. "Last 7 days"
}

/**
 * Emotional Load Flag — raised when nervous system state is activated or
 * dysregulated for 3+ of the last 7 days (WP2 Stage 1 guardrail).
 *
 * MSN-0355: `recorded_days` and `noRecentData` distinguish a genuinely calm
 * window from an empty one. Before this fix the flag could read "Clear"
 * purely because its data source had no rows — an honest reading requires
 * knowing whether there was anything to evaluate at all.
 */
export interface EmotionalLoadFlag {
  raised: boolean;
  activated_days: number;
  dysregulated_days: number;
  /** Days in the window with ANY nervous-system signal recorded (0-7). */
  recorded_days: number;
  /** True when recorded_days is 0 — nothing to evaluate, not "clear". */
  noRecentData: boolean;
  period: string; // e.g. "Last 7 days"
  message: string;
}

/** 7-day and 30-day pattern summary for Medical Bay. */
export interface WeeklyPatternSummary {
  period_7d: {
    strong: number;
    stable: number;
    fragile: number;
    rest: number;
    unknown: number;
  };
  period_30d: {
    stable_or_strong: number;
    total_recorded: number;
  };
  direction: 'settling' | 'steady' | 'variable' | 'insufficient_data';
  direction_label: string;
}

/** Full Recovery Brief — WP7 morning brief format. */
export interface RecoveryBrief {
  stardate: string;
  generated: string; // ISO timestamp
  posture: RecoveryPostureBand;
  posture_message: string;
  sleep_summary: string;
  nervous_system: NervousSystemState;
  energy: string;
  capacity_message: string;
  best_window: string;
  afternoon_note: string;
  guidance: string[];
  load_summary: string;
  active_mission_note: string;
  new_starts_note: string;
  decisions_note: string;
  fleet_summary: string;
}

/**
 * USS-TJR-MSN-0205C/D: VM document processing pipeline + Captain approval
 * queue. Mirrors processing_documents (migrations 0042, 0043).
 */
export type ProcessingStatus =
  | 'received'
  | 'extracted'
  | 'ocr_required'
  | 'ocr_complete'
  | 'classified'
  | 'summarised'
  | 'embedded'
  | 'failed'
  | 'awaiting_review'
  | 'excluded'; // USS-TJR-MSN-0206B: Content Eligibility Engine terminal state

export type DocumentCategory =
  | 'Financial'
  | 'Legal'
  | 'Health'
  | 'Correspondence'
  | 'Reference'
  | 'Identity'
  | 'Property'
  | 'Photo'
  | 'Administrative'
  | 'Other';

export type DocumentSensitivity = 'standard' | 'sensitive' | 'restricted';

export type MemoryRecommendation =
  | 'recommend_full'
  | 'recommend_summary_only'
  | 'recommend_metadata_only'
  | 'recommend_reject'
  | 'needs_review';

export type ReviewDecision =
  | 'approved_metadata'
  | 'approved_summary'
  | 'approved_chunks'
  | 'rejected'
  | 'needs_review';

/** USS-TJR-MSN-0206B: Content Eligibility Engine exclusion reason codes. */
export type ExclusionReason =
  | 'recreational_content'
  | 'unsupported_media'
  | 'temporary_document';

/**
 * USS-TJR-MSN-0206J-1: the CURRENT review workflow state — distinct from
 * `review_decision`, which is a point-in-time decision label. Only
 * 'resolved' and 'rejected' are terminal; 'awaiting_followup' (a
 * 'needs_review' decision) stays open for a later decision.
 */
export type ReviewStatus = 'awaiting_followup' | 'resolved' | 'rejected';

/** One entry in a document's append-only review_history. */
export interface ReviewHistoryEntry {
  decision: ReviewDecision;
  decided_by: string;
  reason: string | null;
  at: string;
  memory_document_id: string | null;
  note?: string; // present on entries backfilled retrospectively by migration 0047
}

export interface ProcessingLogEntry {
  event: string;
  detail: string | null;
  at: string;
}

export interface ProcessingDocument {
  id: string;
  source_name: string;
  source_path: string;
  filename: string;
  file_type: string;
  size_bytes: number | null;
  status: ProcessingStatus;
  extracted_text: string | null;
  ocr_used: boolean;
  ocr_engine: string | null;
  category: DocumentCategory | null;
  tags: string[];
  summary: string | null;
  sensitivity: DocumentSensitivity;
  memory_recommendation: MemoryRecommendation | null;
  chunk_count: number;
  failure_reason: string | null;
  exclusion_reason: ExclusionReason | null;
  processing_log: ProcessingLogEntry[];
  metadata: Record<string, unknown>;
  memory_document_id: string | null;
  review_decision: ReviewDecision | null;
  review_decided_at: string | null;
  review_decided_by: string | null;
  review_reason: string | null;
  review_status: ReviewStatus | null;
  review_history: ReviewHistoryEntry[];
  created_at: string;
  updated_at: string;
}

export interface ProcessingChunk {
  id: string;
  document_id: string;
  chunk_index: number;
  chunk_text: string;
  embedding_model: string | null;
  embedded_at: string | null;
  created_at: string;
}

export interface KnowledgeLibraryStats {
  total_documents: number;
  in_progress: number; // still moving through the processing pipeline, not yet at a terminal status
  ocr_required: number;
  failed_documents: number;
  needs_your_review: number; // status='awaiting_review' AND review_decision IS NULL — actually on the Captain
  memory_approved: number;
  needs_followup: number; // USS-TJR-MSN-0206J-1: review_status = 'awaiting_followup'
  rejected: number;
  decided_today: number; // MSN-0334: review_decided_at falls on today's date — session review progress
}

/**
 * USS-TJR-MSN-0206D: Knowledge Lifecycle Management. Retention
 * classification lives on knowledge_documents (Command Memory, durable),
 * not processing_documents (pre-approval staging) — assigned automatically
 * at approval time (src/lib/retentionPolicy.ts), 'Archived' is the one
 * value never auto-assigned.
 */
export type RetentionPolicy = 'Permanent' | 'Long-Term' | 'Temporary' | 'Expiring' | 'Archived';
export type ArchiveStatus = 'active' | 'archived';

/**
 * USS-TJR-MSN-0206J-2: Command Memory's own 8-value category taxonomy —
 * deliberately distinct from `DocumentCategory` (the 10-value classifier
 * taxonomy on processing_documents, tuned for the AI classifier's output).
 * Assigned at approval time by src/lib/categoryPropagation.ts.
 */
export type MemoryCategory =
  | 'Health'
  | 'Financial'
  | 'Legal'
  | 'Reference'
  | 'Property'
  | 'Operational Resilience'
  | 'Learning'
  | 'Other';

/** Lifecycle-relevant subset of a knowledge_documents row (list/report view). */
export interface KnowledgeMemoryDocument {
  id: string;
  title: string;
  document_type: string;
  category: MemoryCategory | null;
  tags: string[];
  retention_policy: RetentionPolicy | null;
  expiry_date: string | null;
  archive_status: ArchiveStatus;
  review_due_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface RetentionSummary {
  by_policy: Record<string, number>;
  by_archive_status: Record<string, number>;
  overdue_for_review: number;
  by_category: Record<string, number>; // USS-TJR-MSN-0206J-2
}
