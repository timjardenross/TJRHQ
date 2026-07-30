#!/usr/bin/env python3
"""
MSN-0013D: Knowledge Pack Generation & Distribution
Owner: Knowledge Officer / Coder Agent
Date: 2026-06-08
Purpose: Auto-generate role-based, temporal, and differential knowledge packs
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from enum import Enum


class PackType(Enum):
    """Types of knowledge packs."""
    ROLE_BASED = "role"      # Curated by specialist role
    TEMPORAL = "temporal"     # Recent decisions (this week, this month)
    DIFFERENTIAL = "diff"     # What changed since last review


@dataclass
class Document:
    """Knowledge document."""
    id: str
    title: str
    content: str
    category: str  # 'adr', 'decision', 'runbook', 'design'
    created_at: datetime
    updated_at: datetime
    tags: List[str] = field(default_factory=list)


@dataclass
class KnowledgePack:
    """Curated knowledge pack."""
    pack_type: PackType
    title: str
    role: Optional[str]  # For role-based packs
    summary: str
    documents: List[Document]
    recommendations: List[str]
    generated_at: datetime
    size_bytes: int = 0

    def to_markdown(self) -> str:
        """Convert pack to markdown format."""
        lines = [
            f"# {self.title}",
            f"Generated: {self.generated_at.strftime('%Y-%m-%d %H:%M')}\n",
            f"## Summary\n{self.summary}\n",
        ]

        if self.documents:
            lines.append("## Documents\n")
            for doc in self.documents:
                lines.append(f"### {doc.title}")
                lines.append(f"*Category: {doc.category}*\n")
                lines.append(doc.content[:500] + ("..." if len(doc.content) > 500 else ""))
                lines.append("")

        if self.recommendations:
            lines.append("## Recommendations\n")
            for rec in self.recommendations:
                lines.append(f"- {rec}")

        return "\n".join(lines)


class RoleBasedPackGenerator:
    """Generate role-curated knowledge packs."""

    ROLE_MAPPINGS = {
        "Chief Engineer": {
            "categories": ["adr", "architecture", "deployment"],
            "tags": ["infrastructure", "scalability", "performance"]
        },
        "Knowledge Officer": {
            "categories": ["decision", "runbook"],
            "tags": ["knowledge", "documentation", "process"]
        },
        "Captain": {
            "categories": ["decision", "strategic"],
            "tags": ["strategy", "priority", "roadmap"]
        }
    }

    def generate(
        self,
        role: str,
        all_documents: List[Document],
        max_documents: int = 50
    ) -> KnowledgePack:
        """
        Generate role-based knowledge pack.

        Args:
            role: Specialist role
            all_documents: All available documents
            max_documents: Max documents in pack

        Returns:
            KnowledgePack curated for role
        """
        if role not in self.ROLE_MAPPINGS:
            raise ValueError(f"Unknown role: {role}")

        config = self.ROLE_MAPPINGS[role]
        filtered = [
            doc for doc in all_documents
            if doc.category in config["categories"]
        ][:max_documents]

        summary = self._generate_summary(role, filtered)
        recommendations = self._generate_recommendations(role, filtered)

        pack = KnowledgePack(
            pack_type=PackType.ROLE_BASED,
            title=f"{role} Knowledge Pack",
            role=role,
            summary=summary,
            documents=filtered,
            recommendations=recommendations,
            generated_at=datetime.now()
        )

        return pack

    def _generate_summary(self, role: str, documents: List[Document]) -> str:
        """Generate summary for pack."""
        summaries = {
            "Chief Engineer": (
                f"Your weekly knowledge pack includes {len(documents)} engineering documents "
                "and recent decisions related to infrastructure, deployment strategy, and system design. "
                "Focus on architecture reviews and scalability considerations."
            ),
            "Knowledge Officer": (
                f"Your pack contains {len(documents)} knowledge management and process documents. "
                "Review for completeness and consistency. Ensure all recent decisions are documented."
            ),
            "Captain": (
                f"Strategic decision summary: {len(documents)} key decisions from recent weeks. "
                "Review priority alignment and roadmap consistency."
            )
        }
        return summaries.get(role, f"Knowledge pack for {role} with {len(documents)} documents.")

    def _generate_recommendations(self, role: str, documents: List[Document]) -> List[str]:
        """Generate recommendations for role."""
        recommendations = {
            "Chief Engineer": [
                "Review ADR for architectural alignment",
                "Check deployment runbooks for currency",
                "Validate infrastructure decisions against current roadmap"
            ],
            "Knowledge Officer": [
                "Audit decision documentation completeness",
                "Cross-reference decisions with design documents",
                "Update decision tracker with recent changes"
            ],
            "Captain": [
                "Review strategic alignment of recent decisions",
                "Check priority consistency across domains",
                "Validate roadmap against decision outcomes"
            ]
        }
        return recommendations.get(role, ["Review documents for relevance"])


class TemporalPackGenerator:
    """Generate time-based knowledge packs."""

    def generate(
        self,
        all_documents: List[Document],
        days: int = 7
    ) -> KnowledgePack:
        """
        Generate temporal pack (recent N days).

        Args:
            all_documents: All documents
            days: Include documents updated in last N days

        Returns:
            KnowledgePack with recent documents
        """
        cutoff = datetime.now() - timedelta(days=days)
        recent = [doc for doc in all_documents if doc.updated_at >= cutoff]

        summary = (
            f"Recent activity summary: {len(recent)} documents updated in the last {days} days. "
            "Key focus areas and recent decisions outlined below."
        )

        recommendations = [
            "Review recent decisions for impact assessment",
            "Check for any blocking decisions or dependencies",
            "Validate alignment with ongoing projects"
        ]

        pack = KnowledgePack(
            pack_type=PackType.TEMPORAL,
            title=f"Recent Activity - Last {days} Days",
            role=None,
            summary=summary,
            documents=recent,
            recommendations=recommendations,
            generated_at=datetime.now()
        )

        return pack


class DifferentialPackGenerator:
    """Generate differential packs (what changed since last review)."""

    def __init__(self):
        self.last_review_timestamps = {}

    def generate(
        self,
        role: str,
        all_documents: List[Document]
    ) -> KnowledgePack:
        """
        Generate differential pack for role (changes since last review).

        Args:
            role: Specialist role
            all_documents: All documents

        Returns:
            KnowledgePack with only changed documents
        """
        last_review = self.last_review_timestamps.get(role, datetime.now() - timedelta(days=7))

        changed = [
            doc for doc in all_documents
            if doc.updated_at >= last_review
        ]

        summary = (
            f"Differential update for {role}: {len(changed)} documents changed since last review "
            f"({last_review.strftime('%Y-%m-%d')}). Focus on new and modified documents only."
        )

        recommendations = [
            "Prioritize review of recently modified documents",
            "Check for decision reversals or scope changes",
            "Validate impact of changes on your role"
        ]

        pack = KnowledgePack(
            pack_type=PackType.DIFFERENTIAL,
            title=f"What's Changed - {role}",
            role=role,
            summary=summary,
            documents=changed,
            recommendations=recommendations,
            generated_at=datetime.now()
        )

        # Update last review timestamp
        self.last_review_timestamps[role] = datetime.now()

        return pack


if __name__ == "__main__":
    # Example usage
    sample_docs = [
        Document(
            id="adr_001",
            title="ADR-001: Kubernetes Migration",
            content="Decision to migrate infrastructure to Kubernetes in Q3 2026...",
            category="adr",
            created_at=datetime.now() - timedelta(days=10),
            updated_at=datetime.now() - timedelta(days=10),
            tags=["infrastructure", "scalability"]
        ),
        Document(
            id="dec_015",
            title="DEC-015: Defer Kafka Upgrade",
            content="Decision to defer Kafka upgrade to Q4 due to current project load...",
            category="decision",
            created_at=datetime.now() - timedelta(days=5),
            updated_at=datetime.now() - timedelta(days=2),
            tags=["messaging", "infrastructure"]
        ),
        Document(
            id="runbook_001",
            title="Deployment Runbook",
            content="Step-by-step guide for deploying to production...",
            category="runbook",
            created_at=datetime.now() - timedelta(days=30),
            updated_at=datetime.now() - timedelta(days=1),
            tags=["deployment", "operations"]
        ),
    ]

    # Generate role-based pack
    role_gen = RoleBasedPackGenerator()
    chief_eng_pack = role_gen.generate("Chief Engineer", sample_docs)
    print("=" * 70)
    print("ROLE-BASED PACK (Chief Engineer)")
    print("=" * 70)
    print(chief_eng_pack.to_markdown())

    # Generate temporal pack
    temporal_gen = TemporalPackGenerator()
    recent_pack = temporal_gen.generate(sample_docs, days=7)
    print("\n" + "=" * 70)
    print("TEMPORAL PACK (Last 7 Days)")
    print("=" * 70)
    print(f"Title: {recent_pack.title}")
    print(f"Documents: {len(recent_pack.documents)}")

    # Generate differential pack
    diff_gen = DifferentialPackGenerator()
    diff_pack = diff_gen.generate("Chief Engineer", sample_docs)
    print("\n" + "=" * 70)
    print("DIFFERENTIAL PACK (What Changed)")
    print("=" * 70)
    print(f"Title: {diff_pack.title}")
    print(f"Changed documents: {len(diff_pack.documents)}")
