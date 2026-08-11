-- Migration 0134: track CREATE TABLE for health_daily_logs, activity_logs,
-- health_insights, weight_logs — untracked foundation tables
--
-- Follow-up to the 2026-08-09 Human Systems Workbench fix
-- (.claude/skills/bot-reviews/fixes-2026-08-09/human-systems-fixes.md),
-- which fixed untracked RLS migrations for these same four tables (among
-- others) but explicitly flagged a deeper, separate gap it did not attempt:
-- "health_daily_logs, activity_logs, health_insights, and weight_logs don't
-- have their own CREATE TABLE in any tracked migration at all (predates the
-- migrations directory — a 'foundation' schema applied before version
-- control started)."
--
-- Confirmed live (project cjvrpjwewsrumnbdydgg) on 2026-08-10: grepped all
-- 132 tracked migration files for a CREATE TABLE of any of these four names —
-- zero matches (0091_intelligence_workbench_phase_b.sql, 0006_analytics_
-- health_daily_view.sql, and others reference/alter health_daily_logs and
-- health_insights, but none creates them). Supabase's own list_migrations
-- shows live entries named "health_data_foundation" (2026-06-12),
-- "create_activity_logs" (2026-06-19), and "create_weight_logs" (2026-06-19)
-- with no corresponding file ever committed to this repo — these tables
-- were created directly against production before this migrations directory
-- existed.
--
-- Every column, type, default, CHECK/PK/UNIQUE constraint, and index below
-- was pulled live via information_schema.columns / pg_constraint / pg_indexes
-- and independently verified by building the exact same DDL in a throwaway
-- `verify_scratch` schema, then diffing it column-by-column and constraint-
-- by-constraint against the real `public` tables (zero differences other
-- than the expected schema-qualified sequence name on the bigserial `id`
-- columns) before this file was written. The scratch schema was dropped
-- after verification; no live table was touched during that check.
--
-- This migration does not change live state — the tables already exist —
-- it only makes them reproducible from a fresh clone of this repo.
-- CREATE TABLE IF NOT EXISTS is a no-op against the live database today.
--
-- RLS is included and applied unconditionally (not guarded by to_regclass
-- like 0105/0110/0111, which ran before this migration existed and so would
-- no-op on a from-scratch replay): on a fresh clone, this migration is what
-- first brings these tables into existence, so it must also be what leaves
-- them in the same locked-down state they have live today, independent of
-- migration run order. Reproduces the exact live policies verified via
-- pg_policies: health_daily_logs and activity_logs get full authenticated
-- read/write (matching their live "auth_write"/"Authenticated users can
-- manage..." policies); health_insights and weight_logs get exactly what's
-- live today (health_insights: authenticated read-only, written by
-- service_role which bypasses RLS; weight_logs: full authenticated
-- read/write, already correctly locked down live — see note below).
--
-- Note on weight_logs: the original task framing for this follow-up assumed
-- weight_logs still had permissive live RLS alongside
-- physical_readiness_profiles. Re-verified directly via pg_policies before
-- writing this file: weight_logs' live policy ("Authenticated users can
-- manage weight_logs", FOR ALL TO authenticated) is already correctly
-- locked down — it is NOT permissive today. Only physical_readiness_profiles
-- had a real live RLS gap (fixed separately in
-- 0133_tighten_physical_readiness_profiles_rls.sql). weight_logs' RLS is
-- reproduced here only because, like its table structure, it was never
-- tracked in any committed migration (grepped: zero hits for "weight_logs"
-- outside a comment in 0110_tighten_recovery_pulses_and_activity_logs_rls.sql
-- noting it was deliberately out of scope that night) — this closes that
-- tracking gap without changing live state.

-- ── activity_logs ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS activity_logs (
  id                bigserial   PRIMARY KEY,
  log_date          date        NOT NULL DEFAULT CURRENT_DATE,
  activity_type     text        NOT NULL
                       CONSTRAINT activity_logs_activity_type_check
                       CHECK (activity_type = ANY (ARRAY['walk','swim','physio','stretch','strength','cycle','yoga','other'])),
  duration_minutes  integer,
  intensity         text
                       CONSTRAINT activity_logs_intensity_check
                       CHECK ((intensity = ANY (ARRAY['light','moderate','vigorous'])) OR (intensity IS NULL)),
  completed         boolean     NOT NULL DEFAULT true,
  notes             text,
  source            text        NOT NULL DEFAULT 'manual',
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS activity_logs_log_date_idx ON activity_logs USING btree (log_date DESC);

ALTER TABLE activity_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Authenticated users can manage activity_logs" ON activity_logs;

CREATE POLICY "Authenticated users can manage activity_logs"
  ON activity_logs FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);

-- ── weight_logs ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS weight_logs (
  id           bigserial    PRIMARY KEY,
  log_date     date         NOT NULL DEFAULT CURRENT_DATE,
  weight_kg    numeric(5,2) NOT NULL
                  CONSTRAINT weight_logs_weight_range
                  CHECK ((weight_kg > 0::numeric) AND (weight_kg < 500::numeric)),
  time_of_day  text         DEFAULT 'morning'
                  CONSTRAINT weight_logs_time_check
                  CHECK ((time_of_day = ANY (ARRAY['morning','evening'])) OR (time_of_day IS NULL)),
  notes        text,
  source       text         NOT NULL DEFAULT 'manual',
  created_at   timestamptz  NOT NULL DEFAULT now(),
  CONSTRAINT weight_logs_unique_date UNIQUE (log_date)
);

CREATE INDEX IF NOT EXISTS weight_logs_log_date_idx ON weight_logs USING btree (log_date DESC);

ALTER TABLE weight_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Authenticated users can manage weight_logs" ON weight_logs;

CREATE POLICY "Authenticated users can manage weight_logs"
  ON weight_logs FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);

-- ── health_daily_logs ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS health_daily_logs (
  id                          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  logged_at                   timestamptz NOT NULL DEFAULT now(),
  log_date                    date        NOT NULL DEFAULT CURRENT_DATE,
  pain_score                  smallint
                                 CONSTRAINT health_daily_logs_pain_score_check
                                 CHECK ((pain_score >= 0) AND (pain_score <= 10)),
  pain_location                text,
  pain_notes                   text
                                 CONSTRAINT pain_notes_length
                                 CHECK (char_length(pain_notes) <= 500),
  energy                       text
                                 CONSTRAINT health_daily_logs_energy_check
                                 CHECK (energy = ANY (ARRAY['low','moderate','high'])),
  mood                         text
                                 CONSTRAINT health_daily_logs_mood_check
                                 CHECK (mood = ANY (ARRAY['low','stable','positive'])),
  sleep_hours                  numeric(4,1)
                                 CONSTRAINT health_daily_logs_sleep_hours_check
                                 CHECK ((sleep_hours >= 0::numeric) AND (sleep_hours <= 24::numeric)),
  sleep_quality                 text
                                 CONSTRAINT health_daily_logs_sleep_quality_check
                                 CHECK (sleep_quality = ANY (ARRAY['poor','fair','good'])),
  cpap_used                     boolean,
  cpap_hours                    numeric(4,1)
                                 CONSTRAINT health_daily_logs_cpap_hours_check
                                 CHECK ((cpap_hours >= 0::numeric) AND (cpap_hours <= 24::numeric)),
  movement_notes                text
                                 CONSTRAINT movement_notes_length
                                 CHECK (char_length(movement_notes) <= 300),
  medication_notes              text
                                 CONSTRAINT medication_notes_length
                                 CHECK (char_length(medication_notes) <= 300),
  notes                         text
                                 CONSTRAINT notes_length
                                 CHECK (char_length(notes) <= 1000),
  workload_constraint           text        DEFAULT 'unknown'
                                 CONSTRAINT health_daily_logs_workload_constraint_check
                                 CHECK (workload_constraint = ANY (ARRAY['reduced','modified','normal','unknown'])),
  source                        text        NOT NULL DEFAULT 'manual'
                                 CONSTRAINT health_daily_logs_source_check
                                 CHECK (source = ANY (ARRAY['slack','telegram','manual','import'])),
  created_at                    timestamptz NOT NULL DEFAULT now(),
  work_location                 text
                                 CONSTRAINT health_daily_logs_work_location_check
                                 CHECK (work_location = ANY (ARRAY['home','office','travel','other'])),
  sitting_tolerance_minutes     smallint
                                 CONSTRAINT health_daily_logs_sitting_tolerance_minutes_check
                                 CHECK ((sitting_tolerance_minutes >= 0) AND (sitting_tolerance_minutes <= 600)),
  nervous_system_state          text
                                 CONSTRAINT health_daily_logs_nervous_system_state_check
                                 CHECK (nervous_system_state = ANY (ARRAY['calm','activated','dysregulated'])),
  energy_physical                text
                                 CONSTRAINT health_daily_logs_energy_physical_check
                                 CHECK (energy_physical = ANY (ARRAY['good','moderate','limited','depleted'])),
  energy_cognitive                text
                                 CONSTRAINT health_daily_logs_energy_cognitive_check
                                 CHECK (energy_cognitive = ANY (ARRAY['good','moderate','limited','depleted'])),
  energy_emotional                text
                                 CONSTRAINT health_daily_logs_energy_emotional_check
                                 CHECK (energy_emotional = ANY (ARRAY['good','moderate','limited','depleted'])),
  energy_social                   text
                                 CONSTRAINT health_daily_logs_energy_social_check
                                 CHECK (energy_social = ANY (ARRAY['good','moderate','limited','depleted'])),
  daily_capacity_score            numeric(5,2)
                                 CONSTRAINT health_daily_logs_daily_capacity_score_check
                                 CHECK ((daily_capacity_score >= 0::numeric) AND (daily_capacity_score <= 100::numeric)),
  movement_completed               boolean,
  nutrition_anchors_completed       smallint
                                 CONSTRAINT health_daily_logs_nutrition_anchors_completed_check
                                 CHECK ((nutrition_anchors_completed >= 0) AND (nutrition_anchors_completed <= 10)),
  recovery_actions                  text
);

CREATE UNIQUE INDEX IF NOT EXISTS health_daily_logs_date_uniq ON health_daily_logs USING btree (log_date);
CREATE INDEX IF NOT EXISTS health_daily_logs_logged_at_idx ON health_daily_logs USING btree (logged_at DESC);

COMMENT ON TABLE health_daily_logs IS 'Summary-level daily health check-ins. No clinical data. Privacy boundary enforced via constraints.';

ALTER TABLE health_daily_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "auth_write" ON health_daily_logs;
DROP POLICY IF EXISTS "auth_read" ON health_daily_logs;

CREATE POLICY "auth_write"
  ON health_daily_logs FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE POLICY "auth_read"
  ON health_daily_logs FOR SELECT
  TO authenticated
  USING (true);

-- ── health_insights ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS health_insights (
  id                          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  generated_at                timestamptz NOT NULL DEFAULT now(),
  period_start                 date        NOT NULL,
  period_end                   date        NOT NULL,
  insight_type                  text        NOT NULL
                                 CONSTRAINT health_insights_insight_type_check
                                 CHECK (insight_type = ANY (ARRAY['weekly_summary','pain_trend','energy_trend','sleep_trend','trigger_pattern','activity_correlation','appointment_prep'])),
  summary                       text        NOT NULL,
  supporting_data                jsonb       NOT NULL DEFAULT '{}'::jsonb,
  generated_by                   text        DEFAULT 'manual',
  health_summary_md               text,
  created_at                    timestamptz NOT NULL DEFAULT now(),
  week_start                    date,
  source_table                   text        DEFAULT 'captains_log_entries',
  days_logged                    smallint,
  pain_scores                    jsonb,
  pain_avg                       numeric(4,1),
  pain_trend                     text
                                 CONSTRAINT health_insights_pain_trend_check
                                 CHECK (pain_trend = ANY (ARRAY['improving','stable','worsening','insufficient_data'])),
  sleep_avg                      numeric(4,1),
  sleep_trend                    text
                                 CONSTRAINT health_insights_sleep_trend_check
                                 CHECK (sleep_trend = ANY (ARRAY['improving','stable','worsening','insufficient_data'])),
  energy_modal                   text
                                 CONSTRAINT health_insights_energy_modal_check
                                 CHECK (energy_modal = ANY (ARRAY['Low','Moderate','High'])),
  mood_modal                     text
                                 CONSTRAINT health_insights_mood_modal_check
                                 CHECK (mood_modal = ANY (ARRAY['Low','Stable','Positive'])),
  capacity_avg                   numeric(5,1),
  capacity_trend                 text
                                 CONSTRAINT health_insights_capacity_trend_check
                                 CHECK (capacity_trend = ANY (ARRAY['improving','stable','worsening','insufficient_data'])),
  risk_flags                     jsonb,
  positive_flags                  jsonb,
  auto_health_status               text
                                 CONSTRAINT health_insights_auto_health_status_check
                                 CHECK (auto_health_status = ANY (ARRAY['Green','Amber','Red','Unknown'])),
  decisions_extracted              jsonb,
  narrative_summary                text,
  synthesis_version                 text        DEFAULT '1.0',
  baseline_30d                      jsonb,
  baseline_comparison                jsonb,
  deterministic_findings              jsonb,
  cpap_compliance_rate                 numeric(4,3),
  wins_this_week                      jsonb,
  intention_delivery                   jsonb,
  llm_narrative                        jsonb,
  llm_provider                          text,
  narrative_available                   boolean     DEFAULT false,
  pain_location_analysis                 jsonb,
  mood_trend_30d                         jsonb,
  recovery_status                         text,
  physical_capacity_analysis                jsonb,
  dow_pain_pattern                          jsonb,
  dow_energy_pattern                        jsonb,
  source_articles                           jsonb,
  committed_to_memory                       boolean     DEFAULT false,
  committed_at                              timestamptz,
  reviewed_at                               timestamptz,
  overall_status                            text        DEFAULT 'OK'
                                 CONSTRAINT health_insights_overall_status_check
                                 CHECK (overall_status = ANY (ARRAY['OK','CAUTION','ALERT'])),
  CONSTRAINT period_check CHECK (period_end >= period_start)
);

CREATE INDEX IF NOT EXISTS health_insights_generated_at_idx ON health_insights USING btree (generated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS health_insights_period_type_uniq ON health_insights USING btree (period_start, period_end, insight_type);
CREATE INDEX IF NOT EXISTS idx_health_insights_committed ON health_insights USING btree (committed_to_memory, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_insights_reviewed ON health_insights USING btree (reviewed_at DESC) WHERE (reviewed_at IS NOT NULL);
CREATE INDEX IF NOT EXISTS idx_health_insights_week_start ON health_insights USING btree (week_start DESC);

COMMENT ON TABLE health_insights IS 'AI-generated and rule-based health summaries. Feeds Health-Summary.md auto-generation. Source: captains_log_entries.';

ALTER TABLE health_insights ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "auth_read" ON health_insights;

CREATE POLICY "auth_read"
  ON health_insights FOR SELECT
  TO authenticated
  USING (true);
