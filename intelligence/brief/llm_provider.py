"""
LLM provider chain for the daily Captain's Brief digest narrative generation
(2026-08-22: generalized from OR/banking-only narrative to the full daily
digest — world news + every tracked personal domain). Used ONLY for
narrative sections (not classification/ranking).

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
    MISTRAL_DECOMPOSITION_AGENT_ID, MISTRAL_DECOMPOSITION_AGENT_VERSION,
    MISTRAL_ENGINEERING_AGENT_ID, MISTRAL_ENGINEERING_AGENT_VERSION,
    MISTRAL_CHALLENGE_AGENT_ID, MISTRAL_CHALLENGE_AGENT_VERSION,
    MISTRAL_SUMMARY_AGENT_ID, MISTRAL_SUMMARY_AGENT_VERSION,
    MISTRAL_QA_AGENT_ID, MISTRAL_QA_AGENT_VERSION,
    MODEL_ROUTER_URL, OLLAMA_BASE_URL, OLLAMA_MODEL,
)
from core.llm.provider_chain import call_gemini, call_mistral, call_ollama

log = logging.getLogger(__name__)

# 2026-08-22: generalized from a banking/CPS230-only frame to the daily
# educational digest frame. This is the same LLM call chain (Model Router →
# Mistral 4-stage agents → Gemini → Mistral Small → Ollama below) — only the
# framing changed, so every provider in the chain picks it up for free.
_SYSTEM_PROMPT = """You are Captain TJR's daily briefing officer aboard USS Starship Endeavour.
You are generating a daily digest to help him stay educated and informed on what
is happening today — across the wider world (from OSINT/news sources) and across
his own tracked domains (health, engineering, operational resilience, learning,
opportunities).

Rules:
- Only synthesise from the event data provided. Do not invent incidents.
- Be concise, factual, plain English — written to inform and educate, not just alert.
- Explain WHY something matters, not just what happened, so it's genuinely educational.
- Cover every domain present in the input; don't let one domain (e.g. banking/cyber
  OSINT) crowd out the others if multiple are present.
- Use present tense for ongoing events, past tense for resolved events.
- Do not include caveats about your own uncertainty — that is handled by the confidence score.
"""


class LLMProvider:
    """Attempts each provider in preference order. Never raises — returns None on total failure."""

    def check_brief_quality(self, brief_text: str) -> Optional[str]:
        """
        2026-08-22: post-generation sanity check via the QA Validation
        Officer agent — a real LLM pass, not the pure-Python heuristics
        intelligence/audit/brief_qa_agent.py runs (which have no LLM in them
        at all). Non-blocking by design: the caller only logs whatever this
        returns, it never withholds or modifies the brief. Returns None if
        unconfigured or the call fails — never raises.
        """
        if not MISTRAL_API_KEY or not MISTRAL_QA_AGENT_ID:
            return None
        prompt = (
            f"{_SYSTEM_PROMPT}\n\n"
            "You are the QA Validation Officer. Review the finished brief below for one thing "
            "only: is any framing being forced onto content that doesn't warrant it (e.g. general "
            "world news given manufactured 'operational resilience', 'compliance', or 'third-party "
            "risk' language it doesn't actually have)? Reply in 1-2 sentences: either 'OK' with a "
            "short reason, or a specific concern. Do not rewrite the brief.\n\n"
            f"FINISHED BRIEF:\n{brief_text}"
        )
        try:
            return self._call_agent(
                stage="qa-validation",
                agent_id=MISTRAL_QA_AGENT_ID,
                agent_version=int(MISTRAL_QA_AGENT_VERSION),
                prompt=prompt,
            )
        except Exception as exc:
            log.warning("[qa-validation] check failed: %s", exc)
            return None

    def check_risk_rating(self, brief_text: str, overall_risk: str) -> Optional[str]:
        """
        2026-08-22: Risk & Challenge Officer, moved here from the narrative
        pipeline itself (see the comment in _mistral_pipeline for why —
        chaining it as another sequential re-compression stage before the
        Briefing Officer caused fabricated specifics). Reviews the FINISHED
        brief's risk rating adversarially — distinct from check_brief_quality
        above (framing/tone), this checks whether overall_risk is actually
        earned by the events. Non-blocking, log-only. Never raises.
        """
        if not MISTRAL_API_KEY or not MISTRAL_CHALLENGE_AGENT_ID:
            return None
        prompt = (
            f"{_SYSTEM_PROMPT}\n\n"
            "You are the Risk & Challenge Officer. The finished brief below was rated "
            f"'{overall_risk}'. Is that earned by what's actually described, or overstated/"
            "understated? Reply in 1-2 sentences: either 'OK' with a short reason, or a specific "
            "concern. Do not rewrite the brief.\n\n"
            f"FINISHED BRIEF:\n{brief_text}"
        )
        try:
            return self._call_agent(
                stage="risk-challenge",
                agent_id=MISTRAL_CHALLENGE_AGENT_ID,
                agent_version=int(MISTRAL_CHALLENGE_AGENT_VERSION),
                prompt=prompt,
            )
        except Exception as exc:
            log.warning("[risk-challenge] check failed: %s", exc)
            return None

    def generate(self, prompt: str) -> tuple[Optional[str], Optional[str]]:
        """
        Returns (text, provider_name) or (None, None) if all fail.
        """
        providers = [
            ("model-router",            self._model_router),
            ("mistral-4stage-pipeline", self._mistral_pipeline),
            ("gemini-3.5-flash-lite",        self._gemini),
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
        Chains up to 7 Mistral agents (2026-08-22: expanded from 4 — CSD Unit,
        Engineering Officer, and Risk & Challenge Officer were provisioned in
        Mistral but never wired in). Each stage gets a fresh conversation.
        Every stage past Research Scout / Briefing Officer is optional and
        degrades gracefully — a stage failing or its agent id being unset
        just means the pipeline continues with the best output so far, never
        a hard failure. Order: CSD Unit -> Research Scout -> Engineering
        Officer (only if engineering-domain content is present) -> TAO ->
        Risk & Challenge Officer -> Summary Officer -> Briefing Officer.
        """
        if not MISTRAL_API_KEY:
            raise RuntimeError("MISTRAL_API_KEY not set")

        # Require at minimum the Research Scout + Briefing Officer
        if not MISTRAL_RESEARCH_AGENT_ID or not MISTRAL_BRIEFING_AGENT_ID:
            raise RuntimeError("MISTRAL_RESEARCH_AGENT_ID or MISTRAL_BRIEFING_AGENT_ID not configured")

        log.info("[pipeline] Starting Mistral brief pipeline")

        # ── Stage 0: Cognitive Subspace Decomposition Unit (CSD) ─────────────
        # Pre-processing: frame the raw event dump into structured research
        # directives before the Research Scout sees it. Optional — the Scout
        # already handles a raw dump fine, this just gives it a better brief.
        research_input = prompt
        if MISTRAL_DECOMPOSITION_AGENT_ID:
            stage0_prompt = (
                f"{_SYSTEM_PROMPT}\n\n"
                "STAGE 0 — TASK DECOMPOSITION\n"
                "Break the following raw events into structured research directives — one per "
                "domain actually represented (world/OSINT news, health, engineering, operational "
                "resilience, learning, opportunities). Each directive should frame what the Research "
                "Scout should focus on for that domain.\n\n"
                f"{prompt}"
            )
            decomposed = self._call_agent(
                stage="stage0-decomposition",
                agent_id=MISTRAL_DECOMPOSITION_AGENT_ID,
                agent_version=int(MISTRAL_DECOMPOSITION_AGENT_VERSION),
                prompt=stage0_prompt,
            )
            if decomposed:
                log.info("[pipeline] Stage 0 (CSD) complete (%d chars)", len(decomposed))
                research_input = decomposed
            else:
                log.warning("[pipeline] Stage 0 (CSD) failed — continuing with raw event dump")

        # ── Stage 1: Research Scout ──────────────────────────────────────────
        stage1_prompt = (
            f"{_SYSTEM_PROMPT}\n\n"
            "STAGE 1 — RESEARCH SYNTHESIS\n"
            "Review the following events and produce a structured research package. "
            "Identify what is happening, why it matters, and which events have the highest "
            "significance for Captain TJR across whichever domains are represented — world/OSINT "
            "news, health, engineering, operational resilience, learning, opportunities.\n\n"
            f"{research_input}"
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

        # ── Stage 1b: Engineering Officer (domain specialist) ────────────────
        # Only runs when the input actually contains engineering-domain
        # content (daily_digest.py labels its section "Engineering:") — no
        # point spending a call framing an empty section.
        if MISTRAL_ENGINEERING_AGENT_ID and "Engineering:" in prompt:
            stage1b_prompt = (
                f"{_SYSTEM_PROMPT}\n\n"
                "You are the Engineering Officer. The events below include an Engineering section. "
                "Write a short specialist take on the engineering-domain items only — what's "
                "happening and why it matters technically. This will be merged into the wider "
                "research package, not read standalone.\n\n"
                f"{research_input}"
            )
            eng_take = self._call_agent(
                stage="stage1b-engineering",
                agent_id=MISTRAL_ENGINEERING_AGENT_ID,
                agent_version=int(MISTRAL_ENGINEERING_AGENT_VERSION),
                prompt=stage1b_prompt,
            )
            if eng_take:
                log.info("[pipeline] Stage 1b (Engineering Officer) complete (%d chars)", len(eng_take))
                research_package = f"{research_package}\n\nENGINEERING OFFICER NOTES:\n{eng_take}"
            else:
                log.warning("[pipeline] Stage 1b (Engineering Officer) failed — continuing without it")

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

        # 2026-08-22: Risk & Challenge Officer and Summary Officer were tried
        # here as two more sequential re-compression stages after TAO
        # (TAO -> Challenge -> Summary -> Briefing). Isolated per-agent
        # testing showed every stage individually stayed faithful to its
        # input, but the CHAINED result fabricated specifics never present
        # anywhere in the source events ("850ms latency", "7,500-user
        # capacity", "Kubernetes clusters" — none of that was real). Root
        # cause: TAO already does "challenge + compress" as one designed
        # unit (see root .env's original comment — Challenge/Summary were
        # marked "not used in pipeline" for exactly this reason before
        # today). Re-summarizing an already-compressed, caveat-stripped
        # package twice more gives the final Briefing Officer a vaguer input
        # and more room to confabulate confident-sounding filler. Reverted
        # to TAO as the single compression checkpoint; Risk & Challenge
        # Officer is still used, just moved to a POST-generation check on
        # the finished brief (see check_brief_quality() below and
        # brief_generator.py) where it can only flag, never corrupt the
        # input to the stage that actually writes the brief. Summary
        # Officer is left configured but unused in this pipeline, same as
        # it was before this session — TAO already fills that role.
        briefing_input = tao_output if tao_output else research_package

        stage4_prompt = (
            f"{_SYSTEM_PROMPT}\n\n"
            "STAGE 3 — EXECUTIVE BRIEF GENERATION\n"
            "You have received a compressed intelligence package. "
            "Generate the final executive brief for Captain TJR.\n\n"
            f"INTELLIGENCE PACKAGE:\n{briefing_input}\n\n"
            "Respond with a JSON object containing exactly these keys:\n"
            "{\n"
            '  "executive_snapshot": "<2-3 sentence overall summary of the period — cover every domain '
            'actually present (world/OSINT news, health, engineering, operational resilience, learning, '
            'opportunities), don\'t let one domain crowd out the others>",\n'
            '  "emerging_themes": ["<theme 1>", "<theme 2>", "<theme 3>"],\n'
            '  "forward_watch": ["<upcoming item to watch 1>", "<upcoming item to watch 2>"],\n'
            '  "cps230_implications": ["<operational-resilience/regulatory implication, ONLY if the input '
            'actually contains banking/CPS230-relevant events — empty list otherwise, do not force one>"],\n'
            '  "bottom_line": "<one paragraph, what Captain TJR should know and do today, across all his '
            'domains, in plain educational language>"\n'
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
        """Direct mistral-small-latest chat completions — used when conversations API stalls on tool calls.
        2026-08-22: this path has no search/tool access at all, but the
        agent it's replacing (e.g. Research Scout) may be built around an
        expectation of searched, verified specifics — confirmed live this
        session as the exact mechanism that produced fabricated statistics
        and a fake citation. The explicit no-search notice below is
        defense-in-depth alongside the equivalent instruction added to
        Research Scout's own system prompt on Mistral's console (v24)."""
        no_search_notice = (
            "\n\nNOTE: search is unavailable for this response — you are working from the input "
            "text only, with no ability to verify or look anything up. Do not invent statistics, "
            "percentages, dates, or specific facts (including ones that might be true from general "
            "knowledge) to fill gaps or match an expected format. State plainly that search was "
            "unavailable if relevant, and report only what is directly present in the input below."
        )
        try:
            body = json.dumps({
                "model": "mistral-small-latest",
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT + no_search_notice},
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
