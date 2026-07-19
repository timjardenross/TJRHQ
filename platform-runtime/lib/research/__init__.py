#!/usr/bin/env python3
"""
Research Provider Framework

Implements provider abstraction for research execution.
Supports Mistral, Gemini, and local fallback providers.

Public API:
    ResearchTask — Input specification
    EvidencePack — Output from research
    ResearchProvider — Abstract provider interface
    ResearchProviderRegistry — Provider management and fallback
"""

from research_provider import (
    ResearchTask,
    Citation,
    EvidencePack,
    ResearchStatus,
    ResearchProvider,
    ResearchProviderRegistry,
)

__all__ = [
    "ResearchTask",
    "Citation",
    "EvidencePack",
    "ResearchStatus",
    "ResearchProvider",
    "ResearchProviderRegistry",
]
