"""
LLM provider chain for OR Intelligence brief narrative generation.
Used ONLY for executive narrative sections (not classification/ranking).

Provider order (MSN-0209 — local-first):
  0. Model Router :8891/api/model/intelligence-brief (local, preferred — 80% of briefs)
  1. Mistral 4-stage pipeline (cloud + web search — for enriched runs when router unavailable)
       Stage 1 — Research Scout   : synthesise raw events into research package
       Stage 2 — TAO              : challenge + compress (web search OFF)
       Stage 3 — Briefing Officer : produce final executive brief JSON
  2. Gemini 2.5 Flash             (cloud overflow)
  3. Mistral Small                (cloud overflow)
  4. Ollama qwen3:8b              (local last resort)

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
    MISTRAL_TAO_AGENT_ID, MISTRAL_TAO_AGENT_VERSION,
    MISTRAL_BRIEFING_AGENT_ID, MISTRAL_BRIEFING_AGENT_VERSION,
    MODEL_ROUTER_URL, OLLAMA_BASE_URL, OLLAMA_MODEL,
)
from core.llm.provider_chain import call_gemini, call_mistral, call_ollama

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
            ("model-router",            self._model_router),
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

    # ─── Model Router (tier-0 — local, preferred) ────────────────────────────

    def _model_router(self, prompt: str) -> Optional[str]:
        """
        Call Model Router :8891/api/model/intelligence-brief.
        Logs WARNING when falling through so the Captain can see local vs cloud usage.
        """
        url = f"{MODEL_ROUTER_URL.rstrip('/')}/api/model/intelligence-brief"
        body = json.dumps({"prompt": prompt}).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            raise RuntimeError(f"Model Router unavailable: {exc}") from exc

        text = (data.get("response") or data.get("content") or "").strip()
        if not text:
            raise RuntimeError("Model Router returned an empty response")
        return text

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

        # ── Stage 2: Tactical Analysis Officer (TAO) ─────────────────────────
        # Single agent combining challenge review + summary compression (web search OFF)
        tao_output = None
        if MISTRAL_TAO_AGENT_ID:
            stage2_prompt = (
                f"{_SYSTEM_PROMPT}\n\n"
                "You have received a research package from the Endeavour Research Scout. "
                "Apply your full tactical analysis protocol — challenge the findings, then compress.\n\n"
                f"RESEARCH PACKAGE:\n{research_package}"
            )
            tao_output = self._call_agent(
                stage="stage2-tao",
                agent_id=MISTRAL_TAO_AGENT_ID,
                agent_version=int(MISTRAL_TAO_AGENT_VERSION),
                prompt=stage2_prompt,
            )
            if tao_output:
                log.info("[pipeline] Stage 2 (TAO) complete (%d chars)", len(tao_output))
            else:
                log.warning("[pipeline] Stage 2 (TAO) failed — continuing with raw research package")

        # ── Stage 3: Briefing Officer ─────────────────────────────────────────
        # Use TAO output if available, otherwise fall back to raw research package
        briefing_input = tao_output if tao_output else research_package

        stage4_prompt = (
            f"{_SYSTEM_PROMPT}\n\n"
            "STAGE 3 — EXECUTIVE BRIEF GENERATION\n"
            "You have received a compressed intelligence package from the Tactical Analysis Officer. "
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

        log.info("[pipeline] Stage 3 (Briefing) complete (%d chars) — pipeline finished", len(briefing_output))
        return briefing_output

    def _call_agent(
        self,
        stage: str,
        agent_id: str,
        agent_version: int,
        prompt: str,
    ) -> Optional[str]:
        """
        Call a Mistral agent via the conversations API.
        If the agent triggers web_search tool calls and returns no final message
        (conversations API returns intermediate state), fall back to calling
        mistral-small-latest directly via chat completions with the same prompt.
        """
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

                # Agent used tools but conversations API returned no final message.
                # Fall back to direct chat completions on the same underlying model.
                log.warning(
                    "[pipeline] %s returned no final message (tool calls pending) — "
                    "falling back to direct chat completions", stage
                )
                return self._call_mistral_direct(stage, prompt)

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

    def _call_mistral_direct(self, stage: str, prompt: str) -> Optional[str]:
        """Direct mistral-small-latest chat completions — used when conversations API stalls on tool calls."""
        try:
            body = json.dumps({
                "model": "mistral-small-latest",
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
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
            text = data["choices"][0]["message"]["content"].strip()
            log.info("[pipeline] %s direct completions fallback succeeded (%d chars)", stage, len(text))
            return text
        except Exception as exc:
            log.warning("[pipeline] %s direct completions fallback failed: %s", stage, exc)
            return None

    @staticmethod
    def _extract_text(response) -> str:
        """
        Extract assistant text from a Mistral ConversationResponse.

        Agents with web_search tools return multiple ToolExecutionEntry outputs
        before the final MessageOutputEntry. Skip tool entries (they have no
        'role' attribute) and return the first assistant message.
        """
        if hasattr(response, "outputs") and response.outputs:
            for entry in response.outputs:
                # ToolExecutionEntry and similar non-message types lack 'role'
                if getattr(entry, "role", None) != "assistant":
                    continue
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
        return call_gemini(
            _SYSTEM_PROMPT, prompt,
            api_key=GEMINI_API_KEY, max_output_tokens=2048, temperature=0.3, timeout=30,
        )

    # ─── Mistral Small ────────────────────────────────────────────────────────

    def _mistral(self, prompt: str) -> Optional[str]:
        return call_mistral(
            _SYSTEM_PROMPT, prompt,
            api_key=MISTRAL_API_KEY, max_tokens=2048, temperature=0.3, timeout=30,
        )

    # ─── Ollama ───────────────────────────────────────────────────────────────

    def _ollama(self, prompt: str) -> Optional[str]:
        return call_ollama(
            _SYSTEM_PROMPT, prompt,
            base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL,
            temperature=0.3, num_predict=1200, timeout=60,
        )
