-- 0007 — Intelligence Platform RLS Hardening (USS-TJR-MSN-0074 / follow-up)
-- USS Starship Endeavour NCC-170230
--
-- WHY:
--   The five intelligence-platform tables created by 0004 and 0006 were left
--   with Row Level Security DISABLED and zero policies. Because the project's
--   anon / publishable key has table privileges, that meant anyone holding the
--   public key could INSERT / UPDATE / DELETE resilience intelligence. This
--   contradicted docs/SUPABASE_ACCESS_MODEL.md and the ratified decision
--   DEC-20260610-120000 ("RLS remains enabled; backend services use service
--   role; client-side access prohibited").
--
-- WHAT:
--   Enable RLS on all five tables with NO policies (implicit deny). This is the
--   dominant, governance-aligned pattern already used by architecture_records,
--   capabilities, commander_decisions, knowledge_documents, retrieval_logs, etc.
--
-- EFFECT:
--   * service_role (all Python backend writers via CommanderSupabaseClient)
--     BYPASSES RLS — collection, retrofit, and daily sync keep working.
--   * anon / authenticated roles hit implicit deny — no read or write.
--   No policies are added: per the access model, scoped policies are an ADR-gated
--   exception and these tables have no approved client-side consumer.
--
-- Safe to run repeatedly: ENABLE ROW LEVEL SECURITY is idempotent in effect.

alter table intelligence_source_registry enable row level security;
alter table intelligence_source_health   enable row level security;
alter table intelligence_events          enable row level security;
alter table intelligence_briefs          enable row level security;
alter table ori_source_documents         enable row level security;

comment on table ori_source_documents is
  'Raw Daily Operational Resilience Briefs preserved verbatim with full GitHub '
  'attribution (blob_url, content_sha). One row per file version. Extracted '
  'records live in intelligence_events and reference document_id. '
  'RLS enabled (0007), implicit deny — backend-only via service_role.';
