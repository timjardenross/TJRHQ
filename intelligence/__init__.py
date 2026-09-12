"""
Operational Resilience Intelligence Agent
USS Starship Endeavour NCC-170230

Package for collecting, classifying, ranking, and briefing on
operational resilience events relevant to banking, critical infrastructure,
cyber security, and emergency management in the Australian context.

Non-negotiables:
- Ingestion, classification, ranking are 100% rule-based. No LLM dependency.
- LLMs are used only for executive narrative sections (snapshot, themes, etc.).
- All events carry source attribution.
- Source failures are always visible; no silent fallback.
- Mock data is never silently returned.
"""

__version__ = "1.0.0"
__capability__ = "OR-Intelligence-Agent"
