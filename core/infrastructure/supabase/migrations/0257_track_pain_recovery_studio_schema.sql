-- Track the Pain Recovery Studio schema in source control. The live project
-- may already contain these tables; IF NOT EXISTS keeps this migration safe
-- for that environment while making fresh environments reproducible.
CREATE TABLE IF NOT EXISTS public.pain_recovery_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  session_date date NOT NULL, day_state text, chosen_colour text, triggers jsonb NOT NULL DEFAULT '[]'::jsonb,
  valued_activity text, plan text, current_stage text NOT NULL DEFAULT 'morning', current_action text,
  action_status text, adaptation_mode text NOT NULL DEFAULT 'standard', safety_status text NOT NULL DEFAULT 'general_boundary',
  morning_context jsonb NOT NULL DEFAULT '{}'::jsonb, evening_reflection jsonb NOT NULL DEFAULT '{}'::jsonb,
  next_day_cost integer, learning_note text, next_check_in_at timestamptz, active_practice jsonb, practice_step integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(user_id, session_date)
);
CREATE TABLE IF NOT EXISTS public.pain_recovery_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  session_id uuid REFERENCES public.pain_recovery_sessions(id) ON DELETE CASCADE, event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.pain_recovery_reviews (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  week_start date NOT NULL, week_end date NOT NULL, monitoring_score smallint, summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  notes text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.pain_recovery_model_interactions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  session_id uuid REFERENCES public.pain_recovery_sessions(id) ON DELETE SET NULL, provider text NOT NULL,
  model_name text, task_type text NOT NULL DEFAULT 'pain-recovery-guidance', input_context jsonb NOT NULL DEFAULT '{}'::jsonb,
  response jsonb, latency_ms integer, success boolean NOT NULL DEFAULT false, failure_reason text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.pain_recovery_recipe_ingredients (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  domain text NOT NULL, ingredient text NOT NULL, direction text NOT NULL DEFAULT 'high', controllability text NOT NULL DEFAULT 'possible',
  confidence text NOT NULL DEFAULT 'emerging', active boolean NOT NULL DEFAULT true, notes text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.pain_recovery_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pain_recovery_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pain_recovery_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pain_recovery_model_interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pain_recovery_recipe_ingredients ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['pain_recovery_sessions','pain_recovery_events','pain_recovery_reviews','pain_recovery_model_interactions','pain_recovery_recipe_ingredients'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS pain_recovery_owner_all ON public.%I', t);
    EXECUTE format('CREATE POLICY pain_recovery_owner_all ON public.%I FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)', t);
  END LOOP;
END $$;
