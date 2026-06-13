"""
LLM provider chain for OR Intelligence brief narrative generation.
Used ONLY for executive narrative sections (not classification/ranking).

Provider order:
  1. Mistral 4-stage pipeline
       Stage 1 — Research Scout   : synthesise raw events into research package
       Stage 2 — Risk/Challenge   : stress-test findings, surface blind spots
       Stage 3 — Summary Officer  : compress research + challenge into clean package
       Stage 4 — Briefing Officer : produce final executive brief JSON
  2. Gemini 2.5 Flash             (single-shot fallback)
  3. Mistral Small                (single-shot fallback)
  4. Ollama qwen3:8b              (local fallback)

If all LLM providers fail:
  - Events are still collected, classified, ranked, and persisted
  - Brief is generated with narrative_available=False
  - Narrative sections are explicitly None
"""

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Optional

from intelligence.config import (
    GEMINI_API_KEY, MISTRAL_API_KEY,
    MISTRAL_RESEARCH_AGENT_ID, MISTRAL_RESEARCH_AGENT_VERSION,
    MISTRAL_CHALLENGE_AGENT_ID, MISTRAL_CHALLENGE_AGENT_VERSION,
    MISTRAL_SUMMARY_AGENT_ID, MISTRAL_SUMMARY_AGENT_VERSION,
    MISTRAL_BRIEFING_AGENT_ID, MISTRAL_BRIEFING_AGENT_VERSION,
    OLLAMA_BASE_URL, OLLAMA_MODEL,
)

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are the Operational Resilience Intelligence Officer for USS Starship Endeavour.
You are generating sections of an executive intelligence brief for Captain TJR.

Rules:
- Only synthesise from the event data provided. Do not invent incidents.
- Be concise, factual, and use plain English.
- Prioritise Australian banking and CPS 230 implications.
- Use present tense for ongoing events, past tense for resolved events.
- Do not include caveats about your own uncertainty — that is handled by the confidence score.
"""


class LLMProvider:
    """Attempts each provider in preference order. Never raises — returns None on total failure."""

    def generate(self, prompt: str) -> tuple[Optional[str], Optional[str]]:
        """
        Returns (text, provider_name) or (None, None) if all fail.
        """
        providers = [
            ("mistral-4stage-pipeline", self._mistral_pipeline),
            ("gemini-2.5-flash",        self._gemini),
            ("mistral-small",           self._mistral),
            (OLLAMA_MODEL,              self._ollama),
        ]
        for name, fn in providers:
            try:
                result = fn(prompt)
                if result:
                    log.info("LLM narrative generated via %s", name)
                    return result, name
            except Exception as exc:
                log.warning("LLM provider %s failed: %s", name, exc)

        log.warning("All LLM providers failed — narrative will be unavailable")
        return None, None

    # ─── 4-Stage Mistral Pipeline ─────────────────────────────────────────────

    def _mistral_pipeline(self, prompt: str) -> Optional[str]:
        """
        Chains all 4 Mistral agents. Each stage gets a fresh conversation.
        Falls back gracefully if any intermediate stage fails — later stages
        receive whatever the best available input is.
        """
        if not MISTRAL_API_KEY:
            raise RuntimeError("MISTRAL_API_KEY not set")

        # Require at minimum the Research Scout + Briefing Officer
        if not MISTRAL_RESEARCH_AGENT_ID or not MISTRAL_BRIEFING_AGENT_ID:
            raise RuntimeError("MISTRAL_RESEARCH_AGENT_ID or MISTRAL_BRIEFING_AGENT_ID not configured")

        log.info("[pipeline] Starting 4-stage Mistral brief pipeline")

        # ── Stage 1: Research Scout ──────────────────────────────────────────
        stage1_prompt = (
            f"{_SYSTEM_PROMPT}\n\n"
            "STAGE 1 — RESEARCH SYNTHESIS\n"
            "Review the following operational events and produce a structured research package. "
            "Identify what is happening, what the operational significance is, and which events "
            "have the highest potential impact on Australian banking resilience.\n\n"
            f"{prompt}"
        )
        research_package = self._call_agent(
            stage="stage1-research",
            agent_id=MISTRAL_RESEARCH_AGENT_ID,
            agent_version=int(MISTRAL_RESEARCH_AGENT_VERSION),
            prompt=stage1_prompt,
        )
        if not research_package:
            raise RuntimeError("Stage 1 (Research Scout) returned no output")
        log.info("[pipeline] Stage 1 complete (%d chars)", len(research_package))

        # ── Stage 2: Risk/Challenge Officer ──────────────────────────────────
        challenge_output = None
        if MISTRAL_CHALLENGE_AGENT_ID:
            stage2_prompt = (
                f"{_SYSTEM_PROMPT}\n\n"
                "STAGE 2 — RISK & CHALLENGE REVIEW\n"
                "You have received a research package from the Research Scout. "
                "Your role is to stress-test these findings as Risk & Challenge Officer. "
                "Identify any weak signals being over-weighted, under-weighted risks, "
                "gaps in coverage, or events that may escalate. "
                "Be a constructive devil's advocate — push back where the analysis may be incomplete.\n\n"
                f"RESEARCH PACKAGE:\n{research_package}"
            )
            challenge_output = self._call_agent(
                stage="stage2-challenge",
                agent_id=MISTRAL_CHALLENGE_AGENT_ID,
                agent_version=int(MISTRAL_CHALLENGE_AGENT_VERSION),
                prompt=stage2_prompt,
            )
            if challenge_output:
                log.info("[pipeline] Stage 2 complete (%d chars)", len(challenge_output))
            else:
                log.warning("[pipeline] Stage 2 (Risk/Challenge) failed — continuing without challenge layer")
        else:
            log.warning("[pipeline] Stage 2 skipped — MISTRAL_CHALLENGE_AGENT_ID not configured")

        # ── Stage 3: Summary Officer ──────────────────────────────────────────
        summary_output = None
        if MISTRAL_SUMMARY_AGENT_ID:
            stage3_content = f"RESEARCH PACKAGE:\n{research_package}"
            if challenge_output:
                stage3_content += f"\n\nCHALLENGE REVIEW:\n{challenge_output}"

            stage3_prompt = (
                f"{_SYSTEM_PROMPT}\n\n"
                "STAGE 3 — SUMMARY & COMPRESSION\n"
                "You have received a research package and risk challenge review. "
                "Your role as Summary Officer is to compress and prioritise this material "
                "into a clean, actionable intelligence package for the Captain's briefing. "
                "Resolve any tensions between the research and challenge layers. "
                "Retain only what matters for operational resilience decision-making.\n\n"
                f"{stage3_content}"
            )
            summary_output = self._call_agent(
                stage="stage3-summary",
                agent_id=MISTRAL_SUMMARY_AGENT_ID,
                agent_version=int(MISTRAL_SUMMARY_AGENT_VERSION),
                prompt=stage3_prompt,
            )
            if summary_output:
                log.info("[pipeline] Stage 3 complete (%d chars)", len(summary_output))
            else:
                log.warning("[pipeline] Stage 3 (Summary) failed — continuing without summary compression")
        else:
            log.warning("[pipeline] Stage 3 skipped — MISTRAL_SUMMARY_AGENT_ID not configured")

        # ── Stage 4: Briefing Officer ─────────────────────────────────────────
        # Build the richest available input — use summary if available, else research + challenge
        if summary_output:
            briefing_input = summary_output
        elif challenge_output:
            briefing_input = f"RESEARCH:\n{research_package}\n\nCHALLENGE:\n{challenge_output}"
        else:
            briefing_input = research_package

        stage4_prompt = (
            f"{_SYSTEM_PROMPT}\n\n"
            "STAGE 4 — EXECUTIVE BRIEF GENERATION\n"
            "You have received a compressed intelligence package from the Summary Officer. "
            "Generate the final executive brief for Captain TJR.\n\n"
            f"INTELLIGENCE PACKAGE:\n{briefing_input}\n\n"
            "Respond with a JSON object containing exactly these keys:\n"
            "{\n"
            '  "executive_snapshot": "<2-3 sentence overall summary of the intelligence period>",\n'
            '  "emerging_themes": ["<theme 1>", "<theme 2>", "<theme 3>"],\n'
            '  "forward_watch": ["<upcoming risk or watch item 1>", "<upcoming risk or watch item 2>"],\n'
            '  "cps230_implications": ["<implication 1>", "<implication 2>"],\n'
            '  "bottom_line": "<one paragraph, what Captain TJR should know and do>"\n'
            "}\n\n"
            "Only use information from the intelligence package provided. Do not invent incidents."
        )
        briefing_output = self._call_agent(
            stage="stage4-briefing",
            agent_id=MISTRAL_BRIEFING_AGENT_ID,
            agent_version=int(MISTRAL_BRIEFING_AGENT_VERSION),
            prompt=stage4_prompt,
        )
        if not briefing_output:
            raise RuntimeError("Stage 4 (Briefing Officer) returned no output")

        log.info("[pipeline] Stage 4 complete (%d chars) — pipeline finished", len(briefing_output))
        return briefing_output

    def _call_agent(
        self,
        stage: str,
        agent_id: str,
        agent_version: int,
        prompt: str,
    ) -> Optional[str]:
        """Call a single Mistral agent in a fresh conversation. Retries once on transient errors."""
        from mistralai import Mistral
        client = Mistral(api_key=MISTRAL_API_KEY)

        for attempt in range(1, 3):
            try:
                response = client.beta.conversations.start(
                    agent_id=agent_id,
                    agent_version=agent_version,
                    inputs=[{"role": "user", "content": prompt}],
                )
                text = self._extract_text(response)
                if text:
                    return text
                log.warning("[pipeline] %s returned empty response (attempt %d)", stage, attempt)
                return None
            except Exception as exc:
                exc_str = str(exc)
                retryable = any(c in exc_str for c in ("429", "503", "502", "500", "timeout"))
                if attempt == 1 and retryable:
                    log.warning("[pipeline] %s transient error, retrying: %s", stage, exc)
                    time.sleep(3)
                    continue
                log.warning("[pipeline] %s failed: %s", stage, exc)
                return None
        return None

    @staticmethod
    def _extract_text(response) -> str:
        """Extract assistant text from a Mistral ConversationResponse."""
        if hasattr(response, "outputs") and response.outputs:
            for entry in response.outputs:
                if getattr(entry, "role", None) == "assistant":
                    content = getattr(entry, "content", None)
                    if not content:
                        continue
                    if isinstance(content, list):
                        return "".join(
                            c.text if hasattr(c, "text") else str(c)
                            for c in content
                        ).strip()
                    return str(content).strip()
        return ""

    # ─── Gemini 2.5 Flash ─────────────────────────────────────────────────────

    def _gemini(self, prompt: str) -> Optional[str]:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not set")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        )
        body = json.dumps({
            "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.3},
        }).encode()

        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        return candidates[0]["content"]["parts"][0]["text"].strip()

    # ─── Mistral Small ────────────────────────────────────────────────────────

    def _mistral(self, prompt: str) -> Optional[str]:
        if not MISTRAL_API_KEY:
            raise RuntimeError("MISTRAL_API_KEY not set")

        body = json.dumps({
            "model": "mistral-small-latest",
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            "max_tokens": 2048,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            "https://api.mistral.ai/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        return data["choices"][0]["message"]["content"].strip()

    # ─── Ollama ───────────────────────────────────────────────────────────────

    def _ollama(self, prompt: str) -> Optional[str]:
        body = json.dumps({
            "model": OLLAMA_MODEL,
            "prompt": f"{_SYSTEM_PROMPT}\n\n{prompt}",
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 1200},
        }).encode()

        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())

        return data.get("response", "").strip()
