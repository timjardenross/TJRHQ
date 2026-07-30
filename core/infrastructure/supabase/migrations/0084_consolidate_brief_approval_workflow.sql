-- Captain-requested consolidation (2026-07-18): the intelligence_briefs
-- approval workflow had 7 visible stages (IN_REVIEW -> DATA_QA_PASSED ->
-- FACTUAL_QA_PASSED -> ANALYTICAL_QA_PASSED -> QA_READY -> EXECUTIVE_APPROVED
-- -> PUBLISHED) modeled on a 3-person team (Analyst/Intelligence Lead/
-- Executive Approver) per migration 0077's Phase A spec. Live data showed
-- this was never used as designed: of ~15 briefs reviewed, only one was ever
-- published, and its three QA gates (data_qa/factual_qa/analytical_qa) were
-- all passed by the same actor in one sitting — no real differentiation.
-- Every other brief sat permanently at IN_REVIEW with an empty approval_audit.
--
-- Consolidated to 3 states: IN_REVIEW -> QA_PASSED -> PUBLISHED. The three
-- separate QA gate audit entries collapse into one 'qa' entry.

-- ─── 1. Drop the old 7-state CHECK constraint first ──────────────────────────
-- Must happen before the backfill below, since the backfill writes
-- 'QA_PASSED' rows that the old constraint (which predates that value)
-- would reject.
alter table intelligence_briefs
  drop constraint if exists intelligence_briefs_approval_status_check;

-- ─── 2. Backfill existing rows to the new state names ────────────────────────
update intelligence_briefs
set approval_status = 'QA_PASSED'
where approval_status in (
  'DATA_QA_PASSED', 'FACTUAL_QA_PASSED', 'ANALYTICAL_QA_PASSED',
  'QA_READY', 'EXECUTIVE_APPROVED'
);

-- Collapse any existing multi-gate audit entries into a single 'qa' key,
-- keeping the most-advanced gate's approved_by as the record of who
-- actually did the work (matches real data: always the same actor).
update intelligence_briefs
set approval_audit = jsonb_build_object(
  'qa', coalesce(
    approval_audit->'analytical_qa',
    approval_audit->'factual_qa',
    approval_audit->'data_qa'
  )
)
where (approval_audit ? 'data_qa' or approval_audit ? 'factual_qa' or approval_audit ? 'analytical_qa')
  and not (approval_audit ? 'qa');

-- ─── 3. Add the narrower CHECK constraint for the 3 consolidated states ──────
alter table intelligence_briefs
  add constraint intelligence_briefs_approval_status_check
  check (approval_status in ('IN_REVIEW', 'QA_PASSED', 'PUBLISHED'));

comment on column intelligence_briefs.approval_status is
  'Consolidated 3-state workflow (migration 0084, superseding the 0077 '
  '7-state ladder): IN_REVIEW -> QA_PASSED -> PUBLISHED. qa_pass() may be '
  'called by the automated QA agent (actor=system) or the Captain '
  '(actor=intelligence_lead); publish requires actor=executive_approver.';
comment on column intelligence_briefs.approval_audit is
  'Single {"qa": {status, approved_by, details}} entry per brief (migration '
  '0084 consolidated the prior data_qa/factual_qa/analytical_qa 3-gate '
  'structure). Every transition also writes an audit_events row '
  '(category=''mutation'').';
