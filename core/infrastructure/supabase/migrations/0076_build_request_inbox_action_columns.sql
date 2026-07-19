-- MSN-0352: Conversational Governance Enforcement. Adds nullable columns
-- so an AI-proposed operational action (create_mission / create_handoff /
-- log_decision) can be queued in the existing governed build_request_inbox
-- table as an ordinary awaiting_review item, carrying enough structured
-- payload to actually perform the real mutation ONLY on explicit Captain
-- approval via Decide - never before. Existing rows are unaffected
-- (both columns default to null, meaning "a traditional build request,
-- no proposed side-effect to execute on approval").
alter table build_request_inbox
  add column if not exists action_type text,
  add column if not exists action_payload jsonb;

comment on column build_request_inbox.action_type is
  'MSN-0352: when set (create_mission | create_handoff | log_decision), this row is an AI-proposed action awaiting Captain approval in Decide before the real mutation executes. Null for traditional build requests.';
comment on column build_request_inbox.action_payload is
  'MSN-0352: the structured payload to execute on approval, when action_type is set. Never executed automatically - only via POST /api/build-request/[id]/approve-action, which itself is only reachable from Decide approval.';

-- Records the outcome of every execution ATTEMPT for a proposed action -
-- success or failure - not just successes. A failed approval attempt must
-- leave a durable trace, not just an HTTP error the Captain may never see
-- again. Never written until a genuine execution attempt happens (i.e.
-- only from POST /api/build-request/[id]/approve-action).
alter table build_request_inbox
  add column if not exists action_result jsonb;

comment on column build_request_inbox.action_result is
  'MSN-0352: {success, detail, executed_at} for the most recent execution attempt of this proposed action. Null until an approval attempt has actually been made.';
