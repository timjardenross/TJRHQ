"""
Intelligence Audit Module
Three-track audit of Phase A enrichment pipeline:
1. Source Fidelity — signal-to-noise per source
2. Enrichment Validation — scoring/tiering accuracy
3. Brief Coherence — narrative quality and alignment
"""

from .source_fidelity import source_fidelity_report, print_fidelity_report
from .enrichment_validation import (
    enrichment_sample,
    enrichment_stats,
    print_enrichment_validation_template,
    print_enrichment_stats,
)
from .brief_coherence import (
    brief_sample,
    brief_coherence_checks,
    print_brief_coherence_template,
    print_brief_stats,
)

__all__ = [
    "source_fidelity_report",
    "print_fidelity_report",
    "enrichment_sample",
    "enrichment_stats",
    "print_enrichment_validation_template",
    "print_enrichment_stats",
    "brief_sample",
    "brief_coherence_checks",
    "print_brief_coherence_template",
    "print_brief_stats",
]
