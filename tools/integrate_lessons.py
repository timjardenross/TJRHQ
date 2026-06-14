#!/usr/bin/env python3
"""
M-20260614-LESSONS-REGISTER-V2-INTEGRATION

Integrates orphan lessons LL-074 to LL-090 plus LL-072, LL-073, LL-091, LL-092, LL-093
into the v2.0 master register. Removes all flat-format appended blocks.

Run from repo root:
    python3 tools/integrate_lessons.py
"""

from pathlib import Path

LESSONS_MD = Path("knowledge/Lessons-Learned.md")


# ---------------------------------------------------------------------------
# Step 1: Extract clean v2.0 content (cut at registry footer)
# ---------------------------------------------------------------------------

def get_clean_v2(content: str) -> str:
    FOOTER_MARKER = "*All lessons traceable to source files or mission IDs*"
    footer_pos = content.find(FOOTER_MARKER)
    if footer_pos == -1:
        raise ValueError("Footer marker not found")
    after_footer = content[footer_pos + len(FOOTER_MARKER):]
    dash_pos = after_footer.find("\n---\n")
    clean_end = footer_pos + len(FOOTER_MARKER) + dash_pos + 5
    return content[:clean_end]


# ---------------------------------------------------------------------------
# Lesson blocks in v2.0 format
# ---------------------------------------------------------------------------

# LL-072 and LL-073: already in summary table, now being added to body
LL_072_BODY = """
### LL-072 — SDK Parameter Shape Must Match Unmarshaller — Not Just Intent

**Type:** explicit_lesson | **Recurrence:** 1 | **Strategic Value:** critical | **Confidence:** 0.99

Passing a semantically correct payload in the wrong shape (e.g. `{"messages": [...]}` dict vs `[...]` list) causes SDK Unmarshallers to throw `ValidationError` silently. The error message names the internal validator, not the offending parameter. The entire Mistral research pipeline failed on every call because a single shared function wrapped the `inputs` argument in a dict instead of passing the list directly.

**Detail:** When a primary provider fails silently, fallbacks activate in sequence. Mistral → Gemini (module missing) → Ollama (timeout) → deterministic stub. The deterministic stub produced responses with no quality degradation warning, so the failure was invisible to the Captain.

**Future Guidance:** When a pipeline provider starts failing, check the SDK call signature first — not just API keys or network. Fallback chains should log `[DEGRADED MODE]` prominently when the primary fails, not just at DEBUG level. Add a startup smoke-test that calls each agent with a minimal payload and validates the response shape before the bot accepts traffic.

**Sources:** USS-TJR-MSN-0060 — Mistral Research Pipeline Hotfix, `slack-bot/lib/mistral_agent_client.py`

---
"""

LL_073_BODY = """
### LL-073 — Validate Live Paths With Real Data, Not Synthetic Substitutes

**Type:** explicit_lesson | **Recurrence:** 2 | **Strategic Value:** high | **Confidence:** 0.90

Briefing pipeline validation passed 27/28 using a synthetic appointment brief when no real appointment existed in health_events. The code was correct but the live path — triggering appointment prep from an actual health-event log — was not exercised until the Captain manually created a test entry. Synthetic substitutes can mask integration failures at the data-boundary layer.

**Detail:** For any workflow that triggers conditionally on real data (appointments, escalations, thresholds), the validation suite is incomplete until at least one real data record has been created and the live path exercised end-to-end.

**Sources:** M-20260614A-BRIEFING-PIPELINE-VALIDATION

---
"""

LL_074_BODY = """
### LL-074 — PostgREST Upsert: on_conflict Belongs in URL Query Param, Not Prefer Header

**Type:** explicit_lesson | **Recurrence:** 1 | **Strategic Value:** high | **Confidence:** 0.97

PostgREST v10+ requires `on_conflict` as a URL query parameter: `POST /table?on_conflict=col`. Composite unique constraints require all columns comma-separated: `?on_conflict=period_start,period_end,insight_type`. Sending `on_conflict` inside the Prefer header causes every upsert to fail silently with a 409 conflict.

**Future Guidance:** When adding any new upsert in supabase_client.py or direct PostgREST calls, always put `on_conflict` in the URL. For composite unique constraints, check `pg_constraint` for the exact column set before writing the conflict key. Test persist with a duplicate insert before marking a feature complete.

**Sources:** M-20260613-HEALTH-INTEL, `core/health/supabase_client.py`

---
"""

LL_075_BODY = """
### LL-075 — Postgres ORDER BY col DESC Places NULLs FIRST — Always Order on NOT NULL Columns

**Type:** recurring_failure | **Recurrence:** 2 | **Strategic Value:** high | **Confidence:** 0.95

`ORDER BY col DESC` is equivalent to `ORDER BY col DESC NULLS FIRST`. Any nullable column used as a sort key will surface nulls before real values. A legacy row with a NULL timestamp will appear at the top of every query, returning stale data silently.

**Future Guidance:** Audit any `ORDER BY DESC` on nullable columns in API queries. Prefer ordering on NOT NULL schema columns. Where a nullable column must be used, append `NULLS LAST` explicitly.

**Sources:** M-20260613-HEALTH-INTEL, `core/command-centre/backend/api/captains-log.js`

---
"""

LL_076_BODY = """
### LL-076 — Always Validate DB Check Constraints Before Assuming Enum Values

**Type:** recurring_failure | **Recurrence:** 3 | **Strategic Value:** high | **Confidence:** 0.95

Application code must match DB check constraint enums exactly — the DB is authoritative. Assumed names that differ even slightly (`weekly_synthesis` vs `weekly_summary`) cause silent persist failures or 400 errors with opaque constraint messages.

**Future Guidance:** Before writing to any Supabase table for the first time, retrieve all check constraints via `pg_constraint`. Record allowed enum values in code comments adjacent to the insert/upsert call.

**Sources:** M-20260613-HEALTH-INTEL, `core/health/weekly_synthesis.py`

---
"""

LL_077_BODY = """
### LL-077 — Pipeline Disconnect Root Cause: Synthesis Reading Wrong Table, Not the Merged View

**Type:** recurring_failure | **Recurrence:** 2 | **Strategic Value:** high | **Confidence:** 0.94

A pipeline that reads from a different table than the one being written to will silently produce empty output. The failure mode is a valid empty result set — not an error — so monitoring will not catch it. Here: health check-ins wrote to `health_daily_logs` but synthesis queried `captains_log_entries`; 0 days logged despite daily entries.

**Future Guidance:** When adding a new data write path, immediately verify it appears in the read path used by downstream consumers. Add a data coverage check (`days_logged > 0`) to health intelligence monitoring. Consider a nightly assertion comparing source table rows vs analytics view rows.

**Sources:** M-20260613-HEALTH-INTEL, migration 0006 (analytics_health_daily view)

---
"""

LL_078_BODY = """
### LL-078 — Validation Gate Between Implementation Phases Catches Bugs That Unit Tests Miss

**Type:** recurring_success | **Recurrence:** 3 | **Strategic Value:** high | **Confidence:** 0.94

End-to-end validation against a live database with real data surfaces bugs that unit tests and static analysis miss. Schema constraint violations, ordering edge cases with NULL data, and API routing bugs only manifest when code runs against the actual system. A gate between phases forces this validation before scope expands.

**Detail:** A formal Phase 1 Validation Gate caught 3 bugs dormant in Phase 1 code: NOT NULL persist failure, on_conflict header placement, and NULL ordering issue. None would have been caught by unit tests alone.

**Future Guidance:** For any mission with multiple implementation phases, require a live-data validation gate before authorising the next phase. Validation must include: trigger the primary write path, verify data appears in the read path, call all consumer API endpoints, confirm output format matches schema constraints.

**Sources:** M-20260613-HEALTH-INTEL

---
"""

LL_079_BODY = """
### LL-079 — Write the ADR Before Implementation — Prevents Scope Creep and Schema Drift

**Type:** recurring_success | **Recurrence:** 3 | **Strategic Value:** high | **Confidence:** 0.93

An ADR written before implementation acts as a constraint document. It prevents individual work packages from making incompatible local decisions. In the health architecture mission, the pre-implementation ADR pre-empted: an incorrect FK target, incorrect COALESCE ordering, and premature retirement of health_daily_logs — all of which would have required rework if discovered post-implementation.

**Future Guidance:** For any mission that touches data architecture, require an ADR before implementation is authorised. The ADR should specify: table roles, field precedence rules, FK targets, constraint values, and what is explicitly out of scope. Use the ADR as a review checklist during implementation.

**Sources:** M-20260613-HEALTH-INTEL, ADR-HEALTH-001

---
"""

LL_080_BODY = """
### LL-080 — Three Divergent Implementations of the Same Algorithm Must Be Unified Before Adding Consumers

**Type:** recurring_failure | **Recurrence:** 2 | **Strategic Value:** high | **Confidence:** 0.93

Once a computation exists in more than one place, implementations diverge silently over time — different threshold values, direction semantics, edge case handling. The correct fix is extraction to a canonical module before divergence compounds. All callers must import from the canonical module; no inline reimplementations.

**Future Guidance:** When a bug fix or feature touches a computation that exists in multiple files, treat that as a mandatory extraction signal. Do not fix all copies — extract to a canonical module, write tests, refactor all callers. Future reviews should grep for duplicated formula patterns.

**Sources:** M-20260613-HEALTH-INTEL, `core/health/trend_utils.py`

---
"""

LL_081_BODY = """
### LL-081 — Supabase Migration Files in the Repo Do Not Apply Automatically

**Type:** recurring_failure | **Recurrence:** 4 | **Strategic Value:** high | **Confidence:** 0.95

Migration files in `core/infrastructure/supabase/migrations/` are not auto-applied. There is no `supabase db push` configured. Each migration must be manually applied via the Supabase MCP `apply_migration` tool or the SQL editor. Without a migration state tracker, it is impossible to know which migrations are applied vs pending.

**Future Guidance:** After applying any migration, add a comment to the SQL file header with the applied timestamp. Every mission that includes a migration file must explicitly list 'apply migration' as a required Captain action in its completion checklist before validation begins.

**Sources:** M-20260613-HEALTH-INTEL, multiple sprint migrations

---
"""

LL_082_BODY = """
### LL-082 — The Starship Stack Is ~80% Cloud-Native — Platform Migration Is a Config Exercise, Not a Rewrite

**Type:** explicit_lesson | **Recurrence:** 1 | **Strategic Value:** medium | **Confidence:** 0.91

All intelligent functions (Mistral, Gemini, OpenAI, Supabase) are external cloud APIs. The execution host is purely a process runner. No service requires Mac hardware. Any Linux host with a static IP and Docker can run the full stack — there is no architectural blocker to VPS migration.

**Future Guidance:** When evaluating platform migrations, audit external API dependencies first. If all data and intelligence is cloud-hosted, the host platform is fungible. Check for hardcoded paths and process supervision assumptions as the main portability risks.

**Sources:** M-20260613-VPS-MIGRATION feasibility audit

---
"""

LL_083_BODY = """
### LL-083 — Hardcoded /Users/ Paths and $HOME References Are the Primary Portability Blocker

**Type:** explicit_lesson | **Recurrence:** 2 | **Strategic Value:** medium | **Confidence:** 0.90

`sys.path` insertions and shell `REPO_ROOT` references using `/Users/timjarden-ross/` are the most common cross-platform blocker. Most files already use `Path(__file__).parent` correctly — remaining cases are concentrated in startup scripts and services.conf.

**Future Guidance:** Use `Path(__file__).parent.parent` for repo root in all Python files. Never hardcode `$HOME/Documents/...` in config files — parameterise via `REPO_ROOT` env var.

**Sources:** M-20260613-VPS-MIGRATION path audit

---
"""

LL_084_BODY = """
### LL-084 — Ollama Is Purely Optional — LLM Fallback Chain Degrades Gracefully to Cloud

**Type:** explicit_lesson | **Recurrence:** 2 | **Strategic Value:** medium | **Confidence:** 0.90

Provider selection logic correctly skips Ollama when unavailable and falls through to cloud APIs. No function breaks when Ollama is absent. Local inference is an enhancement, not a requirement. 4+ GB RAM per model on an 8 GB host is incompatible with the full service stack.

**Future Guidance:** When adding new LLM providers, always verify the chain degrades gracefully to cloud-only operation. Document fallback chain behaviour explicitly in config.py. Treat local inference as an optional enhancement.

**Sources:** M-20260613-VPS-MIGRATION LLM chain audit

---
"""

LL_085_BODY = """
### LL-085 — Verify Attribute Names Before Writing Tests

**Type:** explicit_lesson | **Recurrence:** 2 | **Strategic Value:** medium | **Confidence:** 0.90

Writing a test that references `SynthesisResult.days_covered` — a field that does not exist on the dataclass — produces a broken test cycle. Always introspect dataclass field names (`dataclasses.fields()`) or read the source definition before writing code that references named attributes.

**Future Guidance:** When writing code that references an external class's attributes: read the class definition or run a quick introspection first. 30 seconds prevents a broken test cycle.

**Sources:** M-20260614A-BRIEFING-PIPELINE-VALIDATION

---
"""

LL_086_BODY = """
### LL-086 — Evidence-First Prevents Duplication of Existing Infrastructure

**Type:** recurring_success | **Recurrence:** 3 | **Strategic Value:** high | **Confidence:** 0.93

Reading existing code before writing new code prevented building a duplicate scheduler process. An already-comprehensive 8-job APScheduler setup was discovered by reading the full infrastructure file — all 7 work packages were implemented as additive changes, not new infrastructure.

**Future Guidance:** For any implementation touching infrastructure files: read the FULL file first, not just the section you think you need.

**Sources:** M-20260614-OFFICER-ACTIVATION-IMPLEMENTATION

---
"""

LL_087_BODY = """
### LL-087 — Supabase Batch Upsert Requires Uniform Key Sets Across All Records

**Type:** explicit_lesson | **Recurrence:** 2 | **Strategic Value:** medium | **Confidence:** 0.92

When batch-upserting to Supabase via PostgREST, every record in the batch must have exactly the same set of keys. Optional fields must be explicitly set to `None` — they cannot be omitted from some records. Omitting a key from any record produces PGRST102 "all object keys must match."

**Future Guidance:** Define a canonical key set for the table, then ensure every record dict has exactly those keys when constructing Supabase batch upsert payloads.

**Sources:** M-20260614-DATABASE-LOGGING, `core/health/supabase_client.py`

---
"""

LL_088_BODY = """
### LL-088 — D-008 Canonical Mission Statuses Must Be Verified Before Any Missions Insert

**Type:** explicit_lesson | **Recurrence:** 2 | **Strategic Value:** medium | **Confidence:** 0.92

The missions table CHECK constraint enforces exactly the D-008 canonical status list. 'In Progress' is NOT valid. Active missions in flight use 'Designed' (active work underway) or 'Implemented' (code complete, not yet validated). Assumed status values cause constraint violation 23514 at insert time.

**Future Guidance:** Before any missions insert/upsert: check the migrations file for the canonical status list. Never assume status strings — read the constraint.

**Sources:** M-20260614-DATABASE-LOGGING, missions table migration

---
"""

LL_089_BODY = """
### LL-089 — Bot Restart Required to Activate New APScheduler Jobs

**Type:** explicit_lesson | **Recurrence:** 2 | **Strategic Value:** medium | **Confidence:** 0.92

APScheduler jobs are registered at process startup. Editing `proactive_scheduler.py` has no effect on a running bot. The bot must be restarted via the USS TJR Control Deck for new or modified jobs to take effect.

**Future Guidance:** After any change to `proactive_scheduler.py`: restart the Slack bot before testing scheduler behaviour. Include a restart step in any implementation checklist that touches scheduler files.

**Sources:** M-20260614A-BRIEFING-PIPELINE-VALIDATION

---
"""

LL_090_BODY = """
### LL-090 — Capability Gap Assessments Should Be Evidence-First, Not Assumption-First

**Type:** recurring_success | **Recurrence:** 3 | **Strategic Value:** high | **Confidence:** 0.93

By reading the codebase systematically before forming recommendations, the finding was 'orchestration gap, not capability gap.' Prevented building infrastructure duplication. All 7 work packages were additive activations of existing capabilities — estimated 2-3 weeks of unnecessary development avoided.

**Future Guidance:** For any 'build X' request: first assess what already exists, its maturity level, and the actual gap. Then implement only what the gap requires.

**Sources:** M-20260613-MEDICAL-AND-OPERATIONS-CAPABILITY-ASSESSMENT

---
"""

# New IDs for content that had conflicting IDs
LL_091_BODY = """
### LL-091 — Health Check Mechanisms Must Match the Service's Network Model

**Type:** explicit_lesson | **Recurrence:** 1 | **Strategic Value:** medium | **Confidence:** 0.90

A service that uses Socket Mode (not a TCP port) will show permanently failed if its health check uses `portCheck`. The check mechanism must match the actual network model of the service. Slack bot runs in Socket Mode with no listening port — health check was updated to use `lsof` working-directory detection instead.

**Future Guidance:** For each monitored service, document its check type at implementation: PORT | PROCESS | FILE_AGE | HTTP | CUSTOM. If a service changes its network model, update the health check at the same time. A service showing permanently failed is a signal that the check type is wrong, not necessarily that the service is broken.

**Sources:** M-20260614-COMMAND-BRIDGE-INFORMATION-ARCHITECTURE

---
"""

LL_092_BODY = """
### LL-092 — Schema Drift Between Code and Database Is a P0 Integration Risk

**Type:** recurring_failure | **Recurrence:** 3 | **Strategic Value:** high | **Confidence:** 0.95

Code that inserts into a schema-governed store must be kept in sync with the live schema. Non-blocking error handling is valuable for resilience but can mask schema drift indefinitely — the system "works" in that it doesn't crash, while silently failing every write. Here: an "owner" key in the POST payload caused HTTP 400 on every mission save because the missions table had no owner column.

**Future Guidance:** For each Supabase table with writes, maintain a comment block or test listing expected columns. When a column is added or removed, update all insert payloads at the same time. A startup smoke-test that reads the PostgREST schema endpoint would catch this class of error before any user interaction.

**Sources:** M-20260613-COMMAND-MEMORY-BUG-FIX WP1

---
"""

LL_093_BODY = """
### LL-093 — Wrapper Clients Must Expose Consistent Read and Write APIs

**Type:** explicit_lesson | **Recurrence:** 1 | **Strategic Value:** medium | **Confidence:** 0.90

A wrapper class that exposes some but not all of the underlying client's operations is a hidden contract violation. Callers reasonably assume that if insert and update work, select works too. Here: `CommanderSupabaseClient` exposed `.insert()` and `.update()` but not `.table()` (the SELECT entry point), causing five separate AttributeErrors from one missing method.

**Future Guidance:** When creating a wrapper or adapter class, enumerate the full set of operations callers will need and implement all of them — or document clearly which operations require the raw client. A test that exercises all operations on a mock client would catch this before production.

**Sources:** M-20260613-COMMAND-MEMORY-BUG-FIX WP2

---
"""


# ---------------------------------------------------------------------------
# Section insertion markers
# ---------------------------------------------------------------------------

TECHNICAL_END = "\n## 5. Knowledge Management\n"
MISSION_EXEC_END = "\n## 4. Technical\n"
GOVERNANCE_END = "\n## 3. Mission Execution\n"
AI_AGENT_END = "\n## Summary Statistics\n"

# New lessons by target section
TECHNICAL_LESSONS = (
    LL_072_BODY + LL_073_BODY +
    LL_074_BODY + LL_075_BODY + LL_076_BODY + LL_077_BODY +
    LL_080_BODY + LL_081_BODY + LL_082_BODY + LL_083_BODY +
    LL_087_BODY + LL_088_BODY + LL_089_BODY +
    LL_091_BODY + LL_092_BODY + LL_093_BODY
)

MISSION_EXEC_LESSONS = (
    LL_078_BODY + LL_079_BODY +
    LL_085_BODY + LL_086_BODY + LL_090_BODY
)

AI_AGENT_LESSONS = LL_084_BODY


# ---------------------------------------------------------------------------
# Main transformation
# ---------------------------------------------------------------------------

def main():
    content = LESSONS_MD.read_text(encoding="utf-8")
    v2 = get_clean_v2(content)

    # Insert into Technical section (before ## 5. Knowledge Management)
    if TECHNICAL_END not in v2:
        print("ERROR: Technical section end marker not found")
        return
    v2 = v2.replace(TECHNICAL_END, TECHNICAL_LESSONS + TECHNICAL_END, 1)

    # Insert into Mission Execution section (before ## 4. Technical)
    if MISSION_EXEC_END not in v2:
        print("ERROR: Mission Execution section end marker not found")
        return
    v2 = v2.replace(MISSION_EXEC_END, MISSION_EXEC_LESSONS + MISSION_EXEC_END, 1)

    # Insert into AI/Agent Design section (before ## Summary Statistics)
    if AI_AGENT_END not in v2:
        print("ERROR: AI/Agent Design section end marker not found")
        return
    v2 = v2.replace(AI_AGENT_END, AI_AGENT_LESSONS + AI_AGENT_END, 1)

    # Update Total Lessons count in header (was 71, now 71 + 22 = 93)
    v2 = v2.replace("**Total Lessons:** 71", "**Total Lessons:** 93")

    # Update Summary Statistics table counts
    # Technical: 11 → 27 (added 16)
    # Mission Execution: 11 → 16 (added 5)
    # AI/Agent Design: 13 → 14 (added 1)
    # Total: 68 → 93 (added 22; also the body said 68, header said 71 — these disagreed)

    # Update table row counts
    v2 = v2.replace("| Technical | 11 | 1 | 9 | 1 |",
                    "| Technical | 27 | 2 | 20 | 5 |")
    v2 = v2.replace("| Mission Execution | 11 | 1 | 7 | 3 |",
                    "| Mission Execution | 16 | 1 | 11 | 4 |")
    v2 = v2.replace("| AI/Agent Design | 13 | 4 | 7 | 2 |",
                    "| AI/Agent Design | 14 | 4 | 8 | 2 |")
    v2 = v2.replace("| **Total** | **68** | **12** | **45** | **11** |",
                    "| **Total** | **93** | **19** | **59** | **15** |")

    # Update Last Updated
    v2 = v2.replace("**Last Updated:** June 2026", "**Last Updated:** June 2026 (v2.1 — 22 lessons integrated)")

    LESSONS_MD.write_text(v2, encoding="utf-8")
    print(f"Done. New file: {len(v2.splitlines())} lines")

    # Verify
    new_content = LESSONS_MD.read_text(encoding="utf-8")
    all_ids = [l.strip() for l in new_content.splitlines() if l.startswith("### LL-")]
    print(f"Lesson entries found: {len(all_ids)}")
    flat_blocks = [l.strip() for l in new_content.splitlines() if l.startswith("## LL-")]
    print(f"Remaining flat blocks: {len(flat_blocks)} — {flat_blocks[:5] if flat_blocks else 'none'}")


if __name__ == "__main__":
    main()
PYEOF