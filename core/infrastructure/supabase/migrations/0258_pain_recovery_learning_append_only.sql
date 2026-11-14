-- Phase 5: learning records and decisions are event-sourced and immutable.
-- The API only inserts and reads these event types; this trigger also prevents
-- an authenticated owner from mutating them directly through the database.
-- Service maintenance and auth-user cascade deletes run without auth.uid(),
-- allowing retention cleanup without exposing mutation to the product user.
CREATE OR REPLACE FUNCTION public.prevent_pain_recovery_learning_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF auth.uid() IS NOT NULL AND OLD.event_type IN ('learning_record', 'learning_decision') THEN
    RAISE EXCEPTION 'Pain Recovery learning events are append-only';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    RETURN NEW;
  END IF;
  RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS pain_recovery_learning_append_only
  ON public.pain_recovery_events;

CREATE TRIGGER pain_recovery_learning_append_only
  BEFORE UPDATE OR DELETE ON public.pain_recovery_events
  FOR EACH ROW
  EXECUTE FUNCTION public.prevent_pain_recovery_learning_event_mutation();
