"""
Intelligence Audit Module
Three-track audit of Phase A enrichment pipeline:
1. Source Fidelity — signal-to-noise per source
2. Enrichment Validation — scoring/tiering accuracy
3. Brief Coherence — narrative quality and alignment
"""

from .brief_coherence import (
    brief_coherence_checks,
    brief_sample,
    print_brief_coherence_template,
    print_brief_stats,
)
from .enrichment_validation import (
    enrichment_sample,
    enrichment_stats,
    print_enrichment_stats,
    print_enrichment_validation_template,
)
from .source_fidelity import print_fidelity_report, source_fidelity_report

__all__ = [
    "brief_coherence_checks",
    "brief_sample",
    "enrichment_sample",
    "enrichment_stats",
    "print_brief_coherence_template",
    "print_brief_stats",
    "print_enrichment_stats",
    "print_enrichment_validation_template",
    "print_fidelity_report",
    "source_fidelity_report",
]
