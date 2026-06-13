"""
Configuration for the OR Intelligence Agent.
All settings are environment-driven with safe defaults.
"""

import os
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent
ENV_FILE = REPO_ROOT / ".env"

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)
except ImportError:
    pass

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

# Mistral Agents — 4-stage OR Intelligence pipeline
# Stage 1: Endeavour Research Scout  → synthesise raw events into research package
# Stage 2: Risk/Challenge Officer    → stress-test findings, surface risks
# Stage 3: Summary Officer           → compress research + challenge into clean package
# Stage 4: Briefing Officer          → produce final executive brief JSON
MISTRAL_RESEARCH_AGENT_ID      = os.getenv("MISTRAL_RESEARCH_AGENT_ID", "")
MISTRAL_RESEARCH_AGENT_VERSION = os.getenv("MISTRAL_RESEARCH_AGENT_VERSION", "1")

MISTRAL_CHALLENGE_AGENT_ID      = os.getenv("MISTRAL_CHALLENGE_AGENT_ID", "")
MISTRAL_CHALLENGE_AGENT_VERSION = os.getenv("MISTRAL_CHALLENGE_AGENT_VERSION", "0")

MISTRAL_SUMMARY_AGENT_ID      = os.getenv("MISTRAL_SUMMARY_AGENT_ID", "")
MISTRAL_SUMMARY_AGENT_VERSION = os.getenv("MISTRAL_SUMMARY_AGENT_VERSION", "0")

MISTRAL_BRIEFING_AGENT_ID      = os.getenv("MISTRAL_BRIEFING_AGENT_ID", "")
MISTRAL_BRIEFING_AGENT_VERSION = os.getenv("MISTRAL_BRIEFING_AGENT_VERSION", "2")

# ─── Scheduling ───────────────────────────────────────────────────────────────
# Cron expression for scheduled brief generation (default: fortnightly, Monday 06:00 AEST)
SCHEDULE_CRON = os.getenv("OR_INTEL_SCHEDULE_CRON", "0 6 1,15 * *")

# ─── Collection ───────────────────────────────────────────────────────────────

HTTP_TIMEOUT_SECONDS   = int(os.getenv("OR_INTEL_HTTP_TIMEOUT", "15"))
MAX_ITEMS_PER_SOURCE   = int(os.getenv("OR_INTEL_MAX_ITEMS_PER_SOURCE", "20"))
STALE_ITEM_HOURS       = int(os.getenv("OR_INTEL_STALE_ITEM_HOURS", "24"))
BRIEF_PERIOD_DAYS      = int(os.getenv("OR_INTEL_BRIEF_PERIOD_DAYS", "14"))

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
