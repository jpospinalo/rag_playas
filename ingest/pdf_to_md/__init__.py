"""
PDF-to-Markdown pipeline for Spanish coastal/beach legal documents.

Public API — import from this package directly:

    from ingest.pdf_to_md import convert_pdfs_to_markdown, process_single_pdf
    from ingest.pdf_to_md import LegalDocumentProfile, LegalBlock, DocumentQualityReport
"""

from .cleaner import adaptive_cleanup
from .config import (
    BRONZE_PREFIX,
    COASTAL_PATTERN,
    COASTAL_TERMS,
    FOOTNOTE_LEGAL_CONTEXT,
    IMAGE_CONTEXT_RE,
    IMAGE_CONTEXT_WINDOW,
    IMAGE_FALLBACK_KEEP_ENABLED,
    IMAGE_FALLBACK_MAX_KEEP,
    IMAGE_FALLBACK_MIN_AREA,
    IMAGE_LOW_VARIANCE,
    IMAGE_MIN_AREA_KEEP_WITHOUT_CONTEXT,
    IMAGE_REQUIRE_SEMANTIC_CONTEXT,
    IMAGE_RESOLUTION_SCALE,
    INTERNAL_REF_SCORE_THRESHOLD,
    MD_STRUCTURE_RE,
    MIN_IMAGE_PIXELS,
    OCR_CORRECTIONS,
    OCR_NOISE_THRESHOLD,
    RAW_PREFIX,
    REPEATED_FURNITURE_THRESHOLD,
)
from .furniture import detect_repeated_page_furniture, remove_page_furniture, split_into_pages
from .layout import reconstruct_paragraphs, repair_layout_breaks
from .models import DocumentQualityReport, LegalBlock, LegalDocumentProfile
from .pipeline import convert_pdfs_to_markdown, main, process_single_pdf
from .profiler import profile_legal_document
from .quality import evaluate_document_quality
from .references import is_legal_internal_reference
from .segmenter import extract_coastal_legal_entities, segment_legal_sections

__all__ = [
    # Pipeline entry points
    "convert_pdfs_to_markdown",
    "process_single_pdf",
    "main",
    # Stage functions
    "profile_legal_document",
    "adaptive_cleanup",
    "detect_repeated_page_furniture",
    "remove_page_furniture",
    "split_into_pages",
    "is_legal_internal_reference",
    "repair_layout_breaks",
    "reconstruct_paragraphs",
    "segment_legal_sections",
    "extract_coastal_legal_entities",
    "evaluate_document_quality",
    # Models
    "LegalDocumentProfile",
    "LegalBlock",
    "DocumentQualityReport",
    # Config
    "RAW_PREFIX",
    "BRONZE_PREFIX",
    "IMAGE_RESOLUTION_SCALE",
    "MIN_IMAGE_PIXELS",
    "IMAGE_LOW_VARIANCE",
    "IMAGE_CONTEXT_WINDOW",
    "IMAGE_CONTEXT_WINDOW",
    "IMAGE_REQUIRE_SEMANTIC_CONTEXT",
    "IMAGE_MIN_AREA_KEEP_WITHOUT_CONTEXT",
    "IMAGE_FALLBACK_KEEP_ENABLED",
    "IMAGE_FALLBACK_MAX_KEEP",
    "IMAGE_FALLBACK_MIN_AREA",
    "OCR_NOISE_THRESHOLD",
    "REPEATED_FURNITURE_THRESHOLD",
    "INTERNAL_REF_SCORE_THRESHOLD",
    "OCR_CORRECTIONS",
    "MD_STRUCTURE_RE",
    "FOOTNOTE_LEGAL_CONTEXT",
    "IMAGE_CONTEXT_RE",
    "COASTAL_TERMS",
    "COASTAL_PATTERN",
]
