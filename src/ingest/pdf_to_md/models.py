"""
Dataclasses used throughout the PDF-to-Markdown pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LegalDocumentProfile:
    """Profile of a legal document for adaptive processing decisions."""

    is_scanned: bool = False
    repeated_headers: bool = False
    repeated_footers: bool = False
    multi_column: bool = False
    legal_density: float = 0.0
    ocr_noise_score: float = 0.0
    footnote_density: float = 0.0
    coastal_semantic_density: float = 0.0
    heading_consistency: float = 0.0
    total_pages: int = 0
    total_paragraphs: int = 0


@dataclass
class LegalBlock:
    """A semantically segmented block of legal text."""

    section_type: str  # metadata | facts | claims | legal_basis | evidence | analysis | decision | citations
    text: str
    score: float = 0.0
    coastal_relevance: float = 0.0


@dataclass
class DocumentQualityReport:
    """Quality evaluation scores for a processed document."""

    paragraph_score: float = 0.0
    heading_score: float = 0.0
    citation_cleanup_score: float = 0.0
    footer_removal_score: float = 0.0
    ocr_cleanup_score: float = 0.0
    section_segmentation_score: float = 0.0
    coastal_entity_score: float = 0.0
    final_quality: float = 0.0

    processing_time_seconds: float = 0.0
    section_counts: dict[str, int] = field(default_factory=dict)
    entity_count: int = 0
