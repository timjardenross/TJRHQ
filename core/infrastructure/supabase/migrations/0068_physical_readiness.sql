-- Migration 0068 — Physical Readiness MVP
--
-- Adaptive gym decision-support module: readiness check-in -> deterministic
-- workout generation -> mobile runner -> completion log -> core_events.
-- Single-user system (Captain only); RLS policies are permissive `true`
-- checks, matching the pattern in 0064_debrief_sessions.sql.
--
-- Apply: supabase db push (or psql $DATABASE_URL -f 0068_physical_readiness.sql)

-- ── physical_readiness_profiles ───────────────────────────────────────────────
-- One row: Captain's hard-coded health context, gym equipment inventory, and
-- default generation rules. Editable later without a code deploy.

CREATE TABLE IF NOT EXISTS physical_readiness_profiles (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_name          text        NOT NULL,
  health_context_json   jsonb       NOT NULL DEFAULT '{}',
  equipment_context_json jsonb      NOT NULL DEFAULT '{}',
  default_rules_json    jsonb       NOT NULL DEFAULT '{}',
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE physical_readiness_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "physical_readiness_profiles_select" ON physical_readiness_profiles FOR SELECT USING (true);
CREATE POLICY "physical_readiness_profiles_insert" ON physical_readiness_profiles FOR INSERT WITH CHECK (true);
CREATE POLICY "physical_readiness_profiles_update" ON physical_readiness_profiles FOR UPDATE USING (true);

-- ── physical_exercises ────────────────────────────────────────────────────────
-- Personal exercise catalogue. status='avoid' exercises are never selectable
-- by the generator; 'needs_review' are excluded until promoted to 'active'.

CREATE TABLE IF NOT EXISTS physical_exercises (
  id                        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name                      text        NOT NULL,
  equipment                 text        NOT NULL,
  movement_pattern          text        NOT NULL,
  primary_muscles_json      jsonb       NOT NULL DEFAULT '[]',
  secondary_muscles_json    jsonb       NOT NULL DEFAULT '[]',
  difficulty                text        NOT NULL DEFAULT 'beginner'
                              CHECK (difficulty IN ('beginner', 'intermediate', 'advanced')),
  default_sets              int         NOT NULL DEFAULT 2,
  default_reps              int         NOT NULL DEFAULT 10,
  default_duration_minutes  int,
  pain_cautions_json         jsonb       NOT NULL DEFAULT '{}',
  regression                text,
  progression                text,
  video_search_query          text        NOT NULL,
  preferred_video_url         text,
  status                    text        NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'avoid', 'needs_review')),
  created_at                timestamptz NOT NULL DEFAULT now(),
  updated_at                timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS physical_exercises_status_idx ON physical_exercises (status);
CREATE INDEX IF NOT EXISTS physical_exercises_equipment_idx ON physical_exercises (equipment);
CREATE INDEX IF NOT EXISTS physical_exercises_movement_pattern_idx ON physical_exercises (movement_pattern);

ALTER TABLE physical_exercises ENABLE ROW LEVEL SECURITY;
CREATE POLICY "physical_exercises_select" ON physical_exercises FOR SELECT USING (true);
CREATE POLICY "physical_exercises_insert" ON physical_exercises FOR INSERT WITH CHECK (true);
CREATE POLICY "physical_exercises_update" ON physical_exercises FOR UPDATE USING (true);

-- ── physical_readiness_checkins ───────────────────────────────────────────────
-- Today's Readiness screen submission. One per training decision, not per day
-- (the Captain may check readiness more than once, e.g. skip then retry).

CREATE TABLE IF NOT EXISTS physical_readiness_checkins (
  id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  energy_state            text        NOT NULL CHECK (energy_state IN ('green', 'yellow', 'orange', 'red')),
  back_pain               smallint    NOT NULL DEFAULT 0 CHECK (back_pain BETWEEN 0 AND 10),
  knee_pain               smallint    NOT NULL DEFAULT 0 CHECK (knee_pain BETWEEN 0 AND 10),
  ankle_pain              smallint    NOT NULL DEFAULT 0 CHECK (ankle_pain BETWEEN 0 AND 10),
  neck_shoulder_pain      smallint    NOT NULL DEFAULT 0 CHECK (neck_shoulder_pain BETWEEN 0 AND 10),
  general_pain            smallint    NOT NULL DEFAULT 0 CHECK (general_pain BETWEEN 0 AND 10),
  time_available_minutes  smallint    NOT NULL CHECK (time_available_minutes IN (15, 25, 35, 45)),
  session_intent          text        NOT NULL
                            CHECK (session_intent IN ('move_gently', 'build_strength', 'reduce_stress', 'improve_energy', 'maintain_habit')),
  notes                   text,
  created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS physical_readiness_checkins_created_at_idx ON physical_readiness_checkins (created_at DESC);

ALTER TABLE physical_readiness_checkins ENABLE ROW LEVEL SECURITY;
CREATE POLICY "physical_readiness_checkins_select" ON physical_readiness_checkins FOR SELECT USING (true);
CREATE POLICY "physical_readiness_checkins_insert" ON physical_readiness_checkins FOR INSERT WITH CHECK (true);

-- ── physical_workout_sessions ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS physical_workout_sessions (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  readiness_checkin_id  uuid        REFERENCES physical_readiness_checkins(id),
  session_type          text        NOT NULL
                          CHECK (session_type IN (
                            'recovery', 'low_energy_strength', 'balanced_strength',
                            'upper_body_strength', 'lower_body_gentle_strength',
                            'cardio_mobility', 'minimum_viable'
                          )),
  generated_plan_json   jsonb       NOT NULL DEFAULT '{}',
  status                text        NOT NULL DEFAULT 'in_progress'
                          CHECK (status IN ('in_progress', 'completed', 'partially_completed', 'stopped')),
  started_at            timestamptz NOT NULL DEFAULT now(),
  completed_at          timestamptz,
  duration_minutes      int,
  energy_after          text        CHECK (energy_after IN ('green', 'yellow', 'orange', 'red')),
  pain_after_json       jsonb       NOT NULL DEFAULT '{}',
  mood_after            text,
  notes                 text,
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS physical_workout_sessions_created_at_idx ON physical_workout_sessions (created_at DESC);
CREATE INDEX IF NOT EXISTS physical_workout_sessions_status_idx ON physical_workout_sessions (status);

ALTER TABLE physical_workout_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "physical_workout_sessions_select" ON physical_workout_sessions FOR SELECT USING (true);
CREATE POLICY "physical_workout_sessions_insert" ON physical_workout_sessions FOR INSERT WITH CHECK (true);
CREATE POLICY "physical_workout_sessions_update" ON physical_workout_sessions FOR UPDATE USING (true);

-- ── physical_workout_exercise_logs ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS physical_workout_exercise_logs (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  workout_session_id    uuid        NOT NULL REFERENCES physical_workout_sessions(id),
  exercise_id           uuid        REFERENCES physical_exercises(id),
  planned_sets          int,
  planned_reps          int,
  planned_weight         text,
  completed_sets        int,
  completed_reps        int,
  weight_used            text,
  effort_score          smallint    CHECK (effort_score BETWEEN 1 AND 10),
  pain_during            smallint    CHECK (pain_during BETWEEN 0 AND 10),
  skipped               boolean     NOT NULL DEFAULT false,
  skip_reason           text,
  notes                 text,
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS physical_workout_exercise_logs_session_idx ON physical_workout_exercise_logs (workout_session_id);
CREATE INDEX IF NOT EXISTS physical_workout_exercise_logs_exercise_idx ON physical_workout_exercise_logs (exercise_id);

ALTER TABLE physical_workout_exercise_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "physical_workout_exercise_logs_select" ON physical_workout_exercise_logs FOR SELECT USING (true);
CREATE POLICY "physical_workout_exercise_logs_insert" ON physical_workout_exercise_logs FOR INSERT WITH CHECK (true);
CREATE POLICY "physical_workout_exercise_logs_update" ON physical_workout_exercise_logs FOR UPDATE USING (true);
