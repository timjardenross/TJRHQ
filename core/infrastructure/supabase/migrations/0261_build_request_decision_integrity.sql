-- 0261_build_request_decision_integrity.sql
--
-- Decision integrity for build_request_inbox. A request that has been decided
-- (approved or rejected) must not be flipped to the opposite decision by any
-- writer: the existing Decisions page, HQ, a second tab or a script. Today two
-- interfaces can each "decide" the same item and the last write silently wins.
--
-- Narrow by design. Only the two conflicting transitions are refused:
--     approved -> rejected        rejected -> approved
-- Everything else is untouched and stays valid, including:
--     awaiting_review / pending_triage -> approved | rejected   (the decision itself)
--     approved -> awaiting_review                               (Undo)
--     approved -> in_progress / completed / ...                 (engineering lifecycle)
--     any update that leaves status unchanged (action_result, record_path, ...)
--     INSERT (a trigger on UPDATE OF status does not run for inserts)
-- Comparison is case-insensitive because writers disagree on case.
--
-- To change a decision deliberately, undo it first (approved -> awaiting_review),
-- then decide again.
--
-- Rollback:  drop trigger if exists build_request_inbox_guard_decision on public.build_request_inbox;
--            drop function if exists public.build_request_inbox_guard_decision();

create or replace function public.build_request_inbox_guard_decision()
returns trigger
language plpgsql
as $$
begin
  if (lower(coalesce(old.status, '')) = 'approved' and lower(coalesce(new.status, '')) = 'rejected')
     or (lower(coalesce(old.status, '')) = 'rejected' and lower(coalesce(new.status, '')) = 'approved') then
    raise exception 'build_request_inbox %: a decided request cannot be changed from % to % (undo it first)',
      old.request_id, old.status, new.status
      using errcode = 'P0001', hint = 'decision_conflict';
  end if;
  return new;
end;
$$;

drop trigger if exists build_request_inbox_guard_decision on public.build_request_inbox;
create trigger build_request_inbox_guard_decision
  before update of status on public.build_request_inbox
  for each row
  when (old.status is distinct from new.status)
  execute function public.build_request_inbox_guard_decision();
