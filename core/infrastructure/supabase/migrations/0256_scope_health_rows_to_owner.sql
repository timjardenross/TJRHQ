-- Security hardening: legacy health foundation tables previously used
-- USING (true), allowing any authenticated user to read another user's data.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['health_daily_logs','activity_logs','weight_logs','health_insights'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE', t);
      EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON public.%I (user_id)', t || '_user_id_idx', t);
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    END IF;
  END LOOP;
END $$;

DROP POLICY IF EXISTS "Authenticated users can manage activity_logs" ON public.activity_logs;
CREATE POLICY "Authenticated users can manage activity_logs" ON public.activity_logs FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS "Authenticated users can manage weight_logs" ON public.weight_logs;
CREATE POLICY "Authenticated users can manage weight_logs" ON public.weight_logs FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS "auth_write" ON public.health_daily_logs;
CREATE POLICY "auth_write" ON public.health_daily_logs FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS "auth_read" ON public.health_daily_logs;
CREATE POLICY "auth_read" ON public.health_daily_logs FOR SELECT TO authenticated USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "auth_read" ON public.health_insights;
CREATE POLICY "auth_read" ON public.health_insights FOR SELECT TO authenticated USING (auth.uid() = user_id);
