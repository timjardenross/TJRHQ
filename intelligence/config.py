"""
Configuration for the OR Intelligence Agent.
All settings are environment-driven with safe defaults.
"""

import os
import sys
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent
ENV_FILE = REPO_ROOT / ".env"

# Load .env if present. 2026-08-29: migrated off python-dotenv onto
# core/platform/configuration_service.py's load_dotenv_files() — same
# non-override semantics (existing os.environ values win), but drops the
# hard dependency on the dotenv package being installed (previously
# silently no-op'd via ImportError if it wasn't) and reuses the one
# canonical env-loading primitive instead of this module's own copy.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from core.platform.configuration_service import load_dotenv_files
load_dotenv_files([ENV_FILE])

# ─── Supabase ─────────────────────────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# ─── LLM Providers ───────────────────────────────────────────────────────────
# Provider preference order:
# 1. Mistral Research Agent (Endeavour Research Scout)
# 2. Gemini 2.5 Flash  3. Mistral Small  4. Ollama qwen3:8b  5. Rule-based

GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
MISTRAL_API_KEY   = os.getenv("MISTRAL_API_KEY", "")
OLLAMA_BASE_URL   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL      = os.getenv("OLLAMA_INTELLIGENCE_MODEL", "qwen3:8b")
# HQ V1 Integration QA §28 fix: every other Model Router caller in this
# repo (platform-runtime/llm.py, telegram-bots/xo/app.py,
# core/platform/reasoning_engine.py, core/platform/insight_engine.py)
# defaults to port 8891 — the router's own real default
# (core/model-router/app.py's MODEL_ROUTER_PORT). This was the only
# default still pointing at 8080, silently falling through to the cloud/
# Mistral chain on every call unless an out-of-repo .env happened to
# override it, contradicting this file's own documented local-first intent.
MODEL_ROUTER_URL  = os.getenv("MODEL_ROUTER_URL", "http://localhost:8891")

# 2026-08-10 (Firecrawl production provisioning): the Captain's own personal
# Firecrawl account, used ONLY as a last-resort fetch path (via
# intelligence/ingestion/firecrawl_client.py) for sources a plain
# urllib.request fetch cannot reach (Cloudflare/Azure Front Door JS-challenge
# or bot-detection 403s, confirmed live from this production host). Free
# plan: 1,000 scrapes/month HARD CAP shared across all account usage, 2
# concurrent requests max — see
# .claude/skills/bot-reviews/fixes-2026-08-09/firecrawl-production-provisioning.md
# for the real cost math and which sources are approved to use this path.
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")

# Mistral Agents — daily digest pipeline (2026-08-22: expanded from 3 stages
# to use more of the 8 already-provisioned agents; see
# intelligence/brief/llm_provider.py's _mistral_pipeline for exact order).
# Narrative-generation chain (sequential, each feeds the next):
#   CSD Unit → Endeavour Research Scout → Engineering Officer (specialist
#   pass, engineering-domain content only) → TAO (challenge + compress,
#   web search OFF) → Briefing Officer (executive brief JSON)
# Post-generation checks (run on the FINISHED brief, non-blocking, log
# only — never alter or withhold it):
#   QA Validation Officer (forced/mismatched framing) and Risk & Challenge
#   Officer (is the risk rating earned) — see brief_generator.py.
# Summary Officer is configured but NOT used: TAO already does
# "challenge + compress" as one designed unit. Chaining Risk & Challenge
# and Summary as two MORE sequential re-compression stages before Briefing
# Officer was tried and reverted 2026-08-22 — isolated per-agent testing
# showed every stage individually stayed faithful to its input, but the
# chained result fabricated specifics that were never in any source event.
# Moving those two to post-generation checks keeps them useful without
# risking corrupting what the Briefing Officer actually writes from.
MISTRAL_RESEARCH_AGENT_ID      = os.getenv("MISTRAL_RESEARCH_AGENT_ID", "")
MISTRAL_RESEARCH_AGENT_VERSION = os.getenv("MISTRAL_RESEARCH_AGENT_VERSION", "1")

MISTRAL_BRIEFING_AGENT_ID      = os.getenv("MISTRAL_BRIEFING_AGENT_ID", "")
MISTRAL_BRIEFING_AGENT_VERSION = os.getenv("MISTRAL_BRIEFING_AGENT_VERSION", "2")

# Endeavour Tactical Analysis Officer (TAO) — combined challenge + summary, web search OFF
MISTRAL_TAO_AGENT_ID      = os.getenv("MISTRAL_TAO_AGENT_ID", "")
MISTRAL_TAO_AGENT_VERSION = os.getenv("MISTRAL_TAO_AGENT_VERSION", "0")

# Cognitive Subspace Decomposition Unit (CSD) — pre-processing task framing
MISTRAL_DECOMPOSITION_AGENT_ID      = os.getenv("MISTRAL_DECOMPOSITION_AGENT_ID", "")
MISTRAL_DECOMPOSITION_AGENT_VERSION = os.getenv("MISTRAL_DECOMPOSITION_AGENT_VERSION", "1")

# Engineering Officer — engineering-domain specialist (core_events, not OSINT)
MISTRAL_ENGINEERING_AGENT_ID      = os.getenv("MISTRAL_ENGINEERING_OFFICER_AGENT_ID", "")
MISTRAL_ENGINEERING_AGENT_VERSION = os.getenv("MISTRAL_ENGINEERING_OFFICER_AGENT_VERSION", "1")

# Risk & Challenge Officer — web-search-enabled, was excluded from the
# pipeline previously for that reason (see git history on this file /
# .env's old comment); _call_agent()'s existing direct-completions fallback
# now covers the tool-call-stall failure mode, so it's back in as an
# optional adversarial stage — degrades gracefully like every other stage.
MISTRAL_CHALLENGE_AGENT_ID      = os.getenv("MISTRAL_CHALLENGE_AGENT_ID", "")
MISTRAL_CHALLENGE_AGENT_VERSION = os.getenv("MISTRAL_CHALLENGE_AGENT_VERSION", "1")

# Summary Officer — web-search-enabled, same caveat as Risk & Challenge above
MISTRAL_SUMMARY_AGENT_ID      = os.getenv("MISTRAL_SUMMARY_AGENT_ID", "")
MISTRAL_SUMMARY_AGENT_VERSION = os.getenv("MISTRAL_SUMMARY_AGENT_VERSION", "1")

# QA Validation Officer — post-generation check, wired in brief_generator.py, not the narrative pipeline itself
MISTRAL_QA_AGENT_ID      = os.getenv("MISTRAL_QA_VALIDATION_OFFICER_AGENT_ID", "")
MISTRAL_QA_AGENT_VERSION = os.getenv("MISTRAL_QA_VALIDATION_OFFICER_AGENT_VERSION", "1")

# ─── Scheduling ───────────────────────────────────────────────────────────────
# Cron expression for scheduled brief generation (2026-08-22: daily 06:30 AEST,
# after the 06:00 daily_source_collection job — was fortnightly, "0 6 1,15 * *",
# which is why the archive only ever had ~2 real published entries a month).
SCHEDULE_CRON = os.getenv("OR_INTEL_SCHEDULE_CRON", "30 6 * * *")

# Daily incremental sync of the GitHub OR Briefs source (USS-TJR-MSN-0074).
# Upstream briefs publish ~10:00 Melbourne daily; sync 30 min later for headroom.
# Time is interpreted in OR_INTEL_SCHEDULE_TZ (DST-aware, auto AEST/AEDT).
GITHUB_SYNC_CRON = os.getenv("OR_INTEL_GITHUB_SYNC_CRON", "30 10 * * *")
SCHEDULE_TZ      = os.getenv("OR_INTEL_SCHEDULE_TZ", "Australia/Melbourne")
# Optionally regenerate the OR brief right after the daily sync (off by default;
# the full brief pipeline hits all sources + LLM, so leave to the fortnightly job
# unless a daily brief is explicitly wanted).
DAILY_BRIEF_AFTER_SYNC = os.getenv("OR_INTEL_DAILY_BRIEF_AFTER_SYNC", "0") == "1"

# ─── Collection ───────────────────────────────────────────────────────────────

HTTP_TIMEOUT_SECONDS   = int(os.getenv("OR_INTEL_HTTP_TIMEOUT", "15"))
MAX_ITEMS_PER_SOURCE   = int(os.getenv("OR_INTEL_MAX_ITEMS_PER_SOURCE", "20"))
STALE_ITEM_HOURS       = int(os.getenv("OR_INTEL_STALE_ITEM_HOURS", "24"))
# 2026-08-22: was 14 — fine for a fortnightly cadence, wrong for daily.
# At 14 days with a daily cron, each day's digest would re-summarize the
# same rolling 2-week window as yesterday's, near-total overlap. 1 day
# matches the new daily cadence; the weekly report path (generate_weekly_report()
# in captains_brief.py) does its own independent 7-day roll-up already.
BRIEF_PERIOD_DAYS      = int(os.getenv("OR_INTEL_BRIEF_PERIOD_DAYS", "1"))

# Bright Data Web Unlocker API — on-demand rendered-page fetch for sources
# behind bot/CAPTCHA challenges a plain GET can't reach (2026-08-10,
# Captain-provisioned free tier: 5,000 requests/month). See
# intelligence/ingestion/brightdata_fetch.py. No key/zone configured = the
# capability is simply unavailable; callers must handle that, not assume it.
BRIGHTDATA_API_KEY        = os.getenv("BRIGHTDATA_API_KEY", "")
BRIGHTDATA_ZONE            = os.getenv("BRIGHTDATA_ZONE", "web_unlocker1")
BRIGHTDATA_TIMEOUT_SECONDS = int(os.getenv("BRIGHTDATA_TIMEOUT_SECONDS", "45"))

# ─── Ranking ─────────────────────────────────────────────────────────────────

TOP_EVENTS_LIMIT = int(os.getenv("OR_INTEL_TOP_EVENTS_LIMIT", "5"))

RANK_WEIGHTS = {
    "source_priority":       0.25,
    "operational_impact":    0.20,
    "customer_impact":       0.15,
    "banking_relevance":     0.15,
    "cps230_relevance":      0.10,
    "cross_source":          0.10,
    "geography_priority":    0.05,
}

GEOGRAPHY_SCORES = {"AU": 1.0, "APAC": 0.5, "GLOBAL": 0.25}
IMPACT_SCORES    = {"high": 1.0, "medium": 0.5, "low": 0.1}

# ─── Status thresholds ───────────────────────────────────────────────────────

SOURCE_STALE_HOURS = int(os.getenv("OR_INTEL_SOURCE_STALE_HOURS", "6"))

# ─── Content-validity heuristics (USS-TJR-MSN-0339 WP1) ─────────────────────
# Distinguishes "HTTP/parse succeeded" from "the content is real" — see
# MSN-0338 §2/§8 Gap #2/#9 (Telstra/NBN scrapers return generic site
# furniture at ~83% "ok"; Azure/AWS status feeds show "degraded" for a
# correctly-empty quiet period).

# Case-insensitive substrings. Presence anywhere in page text means the page
# is confirming "nothing is currently wrong" in its own words — a real,
# valid, empty result, not a collection failure.
NO_INCIDENT_SENTINEL_PHRASES = [
    "no current major or significant local outages",
    "no known issues",
    "all systems operational",
    "no incidents reported",
]

# Case-insensitive substrings indicating the real content is behind a login/
# address lookup and structurally unreachable anonymously (e.g. Telstra's
# outages page — MSN-0338 §4/§8). Treated as a failed collection, not a
# silently-degraded or falsely-successful one, so the gap stays visible.
AUTH_GATED_SENTINEL_PHRASES = [
    "sign in with your telstra id",
    "sign in to view",
    "log in to check",
]

# Case-insensitive substrings. Titles matching these are known generic site
# furniture/marketing copy repeatedly mis-extracted by fallback link-scraping
# (confirmed identical output on every run since source seeding — MSN-0338 §4).
KNOWN_JUNK_TITLE_SUBSTRINGS = [
    "support in times of need",
    "cyber security & safety",
    "cyber security and safety",
    "helping you when times are tough",
    "nbn business plans",
    "connect to the nbn network",
    # Generic pagination furniture (confirmed live on Fastly Status'
    # incidents page, 2026-08-10 — see
    # .claude/skills/bot-reviews/fixes-2026-08-09/firecrawl-production-provisioning.md).
    "load more",
]

# A block of narrative text extracted from a status page's main heading/paragraph
# is only treated as a real alert if it contains at least one of these — otherwise
# it's assumed to be unrelated marketing/informational copy.
STATUS_NARRATIVE_KEYWORDS = [
    "outage", "incident", "disruption", "restored", "affecting",
    "degraded", "service issue", "unplanned", "resolved", "down",
]
