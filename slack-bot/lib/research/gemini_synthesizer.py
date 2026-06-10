#!/usr/bin/env python3
"""
Gemini Synthesizer — Evidence Synthesis & Final Answer Generation

Combines multiple research results into a synthesized final answer.
Uses Gemini to intelligently merge findings, identify contradictions,
and produce a coherent response to the original mission.

Architecture:
    EvidencePack[] (from TaskExecutor)
        ↓
    GeminiSynthesizer (THIS)
        ├─ Merge citations from all sources
        ├─ Identify contradictions
        ├─ Use Gemini to synthesize answer
        └─ Return FinalAnswer
        ↓
    Slack Integration (Phase 2B.6)

Provider-Agnostic Design:
    - Reads ONLY EvidencePack.to_dict()
    - No provider-specific code
    - Citation merging is provider-independent
    - Synthesis works for results from ANY provider
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

log = logging.getLogger(__name__)


# =====================================================================
# Data Structures
# =====================================================================


@dataclass
class FinalAnswer:
    """Synthesized research result ready for delivery."""

    mission_id: str
    original_query: str
    answer: str
    sources: List[object] = field(default_factory=list)  # List[Citation]
    confidence: float = 0.8  # Confidence in synthesis
    contradiction_notes: Optional[str] = None
    cost_estimate: float = 0.0
    execution_time_ms: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )


# =====================================================================
# Gemini Synthesizer
# =====================================================================


class GeminiSynthesizer:
    """
    Synthesize research evidence into a final answer.

    Features:
    - Merges citations from all evidence packs
    - Identifies source contradictions
    - Uses Gemini to synthesize coherent answer
    - Confidence scoring
    - Cost estimation

    Example:
        synthesizer = GeminiSynthesizer()
        final_answer = synthesizer.synthesize_research(
            mission_id="msn-001",
            original_query="What is APRA CPS 230?",
            evidence_packs=[pack1, pack2, pack3],
            synthesis_instructions="Combine findings into overview"
        )
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.0-flash",
    ):
        """
        Initialize Gemini Synthesizer.

        Args:
            api_key: Gemini API key (default: GEMINI_API_KEY env var)
            model: Gemini model identifier
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model
        self.client = None

        self._init_client()

    def _init_client(self):
        """Initialize Gemini client."""
        if not self.api_key:
            log.warning("[gemini-synthesizer] GEMINI_API_KEY not configured")
            return

        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            self.client = genai.GenerativeModel(self.model)
            log.info("[gemini-synthesizer] Client initialized successfully")
        except ImportError as e:
            log.error(
                f"[gemini-synthesizer] Failed to import Google AI SDK: {e}"
            )
        except Exception as e:
            log.error(
                f"[gemini-synthesizer] Failed to initialize client: {e}"
            )

    def health_check(self) -> bool:
        """
        Check if Gemini API is accessible.

        Returns:
            True if API is reachable, False otherwise
        """
        if not self.client or not self.api_key:
            return False

        try:
            response = self.client.generate_content(
                "test", stream=False
            )
            log.debug("[gemini-synthesizer] Health check passed")
            return True
        except Exception as e:
            log.warning(
                f"[gemini-synthesizer] Health check failed: "
                f"{str(e)[:100]}"
            )
            return False

    def synthesize_research(
        self,
        mission_id: str,
        original_query: str,
        evidence_packs: List[object],  # List[EvidencePack]
        synthesis_instructions: str,
    ) -> FinalAnswer:
        """
        Synthesize evidence into final answer.

        Args:
            mission_id: Mission identifier
            original_query: Original user query
            evidence_packs: List of EvidencePack objects
            synthesis_instructions: How to synthesize (from GeminiXODecomposer)

        Returns:
            FinalAnswer with synthesized result
        """
        if not self.client:
            log.error("[gemini-synthesizer] Client not initialized")
            return FinalAnswer(
                mission_id=mission_id,
                original_query=original_query,
                answer="Error: Synthesis service unavailable",
                confidence=0.0,
            )

        log.info(
            f"[gemini-synthesizer] Synthesizing {len(evidence_packs)} "
            f"evidence packs for mission {mission_id}"
        )

        try:
            # Extract evidence from packs
            evidence_texts = self._extract_evidence_texts(evidence_packs)

            # Merge citations
            all_citations = self._merge_citations(evidence_packs)

            # Detect contradictions
            contradictions = self._detect_contradictions(evidence_packs)

            # Build synthesis prompt
            prompt = self._build_synthesis_prompt(
                original_query,
                evidence_texts,
                synthesis_instructions,
                contradictions,
            )

            # Call Gemini
            response = self.client.generate_content(prompt, stream=False)

            if not response or not response.text:
                raise Exception("Gemini returned empty response")

            # Create final answer
            final_answer = FinalAnswer(
                mission_id=mission_id,
                original_query=original_query,
                answer=response.text,
                sources=all_citations,
                confidence=self._score_confidence(evidence_packs),
                contradiction_notes=contradictions,
                cost_estimate=self._estimate_cost(evidence_packs),
                execution_time_ms=self._sum_latencies(evidence_packs),
            )

            log.info(
                f"[gemini-synthesizer] Synthesis complete: "
                f"confidence={final_answer.confidence}, "
                f"citations={len(all_citations)}"
            )

            return final_answer

        except Exception as e:
            msg = (
                f"Synthesis failed: {type(e).__name__}: "
                f"{str(e)[:100]}"
            )
            log.error(f"[gemini-synthesizer] {msg}")

            return FinalAnswer(
                mission_id=mission_id,
                original_query=original_query,
                answer=f"Error during synthesis: {str(e)[:200]}",
                confidence=0.0,
            )

    def _extract_evidence_texts(
        self,
        evidence_packs: List[object],
    ) -> str:
        """
        Extract evidence text from all packs.

        Args:
            evidence_packs: List of EvidencePack objects

        Returns:
            Formatted evidence text
        """
        texts = []

        for i, pack in enumerate(evidence_packs, 1):
            answer = getattr(pack, "answer", "")
            source = getattr(pack, "provider", "unknown")
            task = getattr(pack, "research_task", "")

            text = f"""Evidence {i} (from {source}):
Task: {task}
Content: {answer}
"""
            texts.append(text)

        return "\n".join(texts)

    def _merge_citations(
        self,
        evidence_packs: List[object],
    ) -> List[object]:
        """
        Merge citations from all evidence packs.

        Args:
            evidence_packs: List of EvidencePack objects

        Returns:
            Merged list of Citation objects
        """
        all_citations = []
        seen_urls = set()

        for pack in evidence_packs:
            citations = getattr(pack, "citations", [])
            for citation in citations:
                url = getattr(citation, "url", None)

                # Avoid duplicates
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)

                all_citations.append(citation)

        log.info(
            f"[gemini-synthesizer] Merged citations: "
            f"{len(all_citations)} unique sources"
        )

        return all_citations

    def _detect_contradictions(
        self,
        evidence_packs: List[object],
    ) -> Optional[str]:
        """
        Detect contradictions between evidence sources.

        Args:
            evidence_packs: List of EvidencePack objects

        Returns:
            String describing contradictions, or None if none found
        """
        if len(evidence_packs) < 2:
            return None

        # Simple heuristic: check if any pack has contradictions flag
        contradictions = []

        for pack in evidence_packs:
            contradiction_flag = getattr(
                pack, "contradiction_detected", None
            )
            if contradiction_flag is True:
                contradictions.append(
                    getattr(pack, "research_task", "unknown")
                )

        if contradictions:
            msg = (
                f"Contradictions detected in: {', '.join(contradictions)}. "
                f"See synthesis for nuanced perspective."
            )
            log.warning(f"[gemini-synthesizer] {msg}")
            return msg

        return None

    def _score_confidence(
        self,
        evidence_packs: List[object],
    ) -> float:
        """
        Calculate confidence score for synthesis.

        Based on:
        - Individual pack confidences
        - Number of sources
        - Agreement between sources

        Args:
            evidence_packs: List of EvidencePack objects

        Returns:
            Confidence score 0.0-1.0
        """
        if not evidence_packs:
            return 0.0

        # Average pack confidences
        avg_confidence = sum(
            getattr(pack, "confidence", 0.5) for pack in evidence_packs
        ) / len(evidence_packs)

        # Boost for multiple sources
        source_boost = min(0.2, len(evidence_packs) * 0.05)

        # Final score
        confidence = min(1.0, avg_confidence + source_boost)

        return round(confidence, 2)

    def _estimate_cost(
        self,
        evidence_packs: List[object],
    ) -> float:
        """
        Estimate total cost from token usage.

        Args:
            evidence_packs: List of EvidencePack objects

        Returns:
            Estimated cost in dollars (rough estimate)
        """
        total_tokens = sum(
            getattr(pack, "tokens_used", 0) or 0
            for pack in evidence_packs
        )

        # Rough estimate: $0.00001 per token
        cost = total_tokens * 0.00001

        return round(cost, 4)

    def _sum_latencies(
        self,
        evidence_packs: List[object],
    ) -> int:
        """
        Sum latencies of all evidence packs.

        Args:
            evidence_packs: List of EvidencePack objects

        Returns:
            Total latency in milliseconds
        """
        return sum(
            getattr(pack, "latency_ms", 0) or 0
            for pack in evidence_packs
        )

    def _build_synthesis_prompt(
        self,
        original_query: str,
        evidence_texts: str,
        synthesis_instructions: str,
        contradictions: Optional[str],
    ) -> str:
        """
        Build prompt for Gemini synthesis.

        Args:
            original_query: Original user query
            evidence_texts: Formatted evidence from all sources
            synthesis_instructions: How to synthesize (from decomposer)
            contradictions: Any detected contradictions

        Returns:
            Formatted prompt string
        """
        prompt = f"""You are an expert research synthesizer.

ORIGINAL QUERY: {original_query}

RESEARCH EVIDENCE:
{evidence_texts}

SYNTHESIS INSTRUCTIONS:
{synthesis_instructions}

{f'IMPORTANT: {contradictions}' if contradictions else ''}

TASK:
Synthesize all evidence into a comprehensive, coherent answer to the original query.
Address each piece of evidence.
If sources disagree, note the different perspectives.
Provide a balanced, nuanced conclusion.

RESPONSE: Clear, well-structured answer that addresses the original query.
"""
        return prompt
