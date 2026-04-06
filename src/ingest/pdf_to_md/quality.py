"""
Automated quality evaluation for processed legal documents.

Scores are computed across six dimensions and combined into a weighted
final quality score (0–100).
"""

from __future__ import annotations

import re
from collections import Counter

from .config import OCR_NOISE_THRESHOLD
from .models import DocumentQualityReport, LegalBlock, LegalDocumentProfile
from .references import is_legal_internal_reference


# ---------------------------------------------------------------------------
# Individual scoring functions
# ---------------------------------------------------------------------------


def _score_paragraph_reconstruction(original: str, cleaned: str) -> float:
    """Score paragraph reconstruction quality.

    Checks both the consolidation ratio (paragraphs removed) and the
    presence of remaining broken paragraphs.
    """
    orig_paras = len([p for p in original.split("\n\n") if p.strip()])
    clean_paras = [p for p in cleaned.split("\n\n") if p.strip()]

    if orig_paras == 0:
        return 50.0

    ratio = len(clean_paras) / orig_paras
    if 0.4 <= ratio <= 0.85:
        consolidation = 50.0
    elif 0.85 < ratio <= 1.0:
        consolidation = 35.0
    else:
        consolidation = 20.0

    broken = sum(
        1
        for i in range(len(clean_paras) - 1)
        if (
            clean_paras[i].strip()
            and clean_paras[i + 1].strip()
            and clean_paras[i].strip()[-1] not in ".;:?!\"')"
            and clean_paras[i + 1].strip()[0].islower()
            and not clean_paras[i + 1].strip().startswith(("#", "-", "*"))
        )
    )
    break_ratio = broken / max(1, len(clean_paras))
    integrity = max(0.0, 50.0 - break_ratio * 200)

    return min(100.0, consolidation + integrity)


def _score_footer_removal(cleaned_md: str) -> float:
    """Score footer/header removal effectiveness on the cleaned text."""
    lines = [line.strip() for line in cleaned_md.splitlines() if line.strip()]
    if not lines:
        return 50.0

    footnote_body_re = re.compile(r"^\d{1,2}\s{2,}")
    remaining = sum(1 for line in lines if footnote_body_re.match(line))
    return max(0.0, min(100.0, 100 - (remaining / len(lines)) * 1000))


def _score_citation_cleanup(cleaned_md: str) -> float:
    """Score internal reference cleanup effectiveness."""
    lines = cleaned_md.splitlines()
    if not lines:
        return 50.0

    remaining_refs = sum(1 for line in lines if is_legal_internal_reference(line))

    simple_fn = re.compile(r"^\s*\d{1,2}\s{2,}(En|Ver|Al|Corte|Consejo|Por|M\.P)", re.IGNORECASE)
    remaining_refs += sum(1 for line in lines if simple_fn.match(line.strip()))

    ref_ratio = remaining_refs / len(lines)
    return max(0.0, min(100.0, 100 - ref_ratio * 800))


def _score_segmentation(blocks: list[LegalBlock]) -> float:
    """Score section segmentation quality."""
    if not blocks:
        return 0.0

    types_found = {block.section_type for block in blocks}
    type_diversity = len(types_found) / 8

    avg_confidence = sum(block.score for block in blocks) / len(blocks)

    coastal_blocks = sum(1 for b in blocks if b.coastal_relevance > 0.1)
    coastal_bonus = min(0.2, coastal_blocks / len(blocks))

    score = (type_diversity * 50) + (avg_confidence * 30) + (coastal_bonus * 100)
    return min(100.0, score)


def _score_entity_extraction(
    entities: dict[str, list[str]],
    profile: LegalDocumentProfile,
) -> float:
    """Score coastal entity extraction quality."""
    types_found = len(entities)
    total_entities = sum(len(values) for values in entities.values())
    expected_types = max(1, profile.coastal_semantic_density * 50)

    coverage = min(1.0, types_found / expected_types)
    richness = min(1.0, total_entities / 10)

    key_terms = {"dimar", "playa", "bajamar", "ocupacion", "espacio_publico"}
    key_bonus = sum(1 for k in key_terms if k in entities) / len(key_terms)

    score = (coverage * 40) + (richness * 30) + (key_bonus * 30)
    return min(100.0, score * 100)


# ---------------------------------------------------------------------------
# Main evaluation entry point
# ---------------------------------------------------------------------------


def evaluate_document_quality(
    original_md: str,
    cleaned_md: str,
    blocks: list[LegalBlock],
    entities: dict[str, list[str]],
    profile: LegalDocumentProfile,
) -> DocumentQualityReport:
    """Evaluate document processing quality.

    Scoring weights:
    - Paragraph reconstruction: 20 %
    - Header/footer cleanup:    15 %
    - OCR correction:           15 %
    - Legal reference cleanup:  10 %
    - Section segmentation:     20 %
    - Coastal entity extraction: 20 %
    """
    paragraph_score = _score_paragraph_reconstruction(original_md, cleaned_md)
    heading_score = profile.heading_consistency * 100

    if profile.ocr_noise_score <= OCR_NOISE_THRESHOLD:
        ocr_score = 100.0
    else:
        ocr_score = max(20.0, 100.0 - ((profile.ocr_noise_score - OCR_NOISE_THRESHOLD) * 200))

    footer_score = _score_footer_removal(cleaned_md)
    citation_score = _score_citation_cleanup(cleaned_md)
    segmentation_score = _score_segmentation(blocks)
    entity_score = _score_entity_extraction(entities, profile)

    final_quality = (
        paragraph_score * 0.20
        + footer_score * 0.15
        + ocr_score * 0.15
        + citation_score * 0.10
        + segmentation_score * 0.20
        + entity_score * 0.20
    )

    section_counts = Counter(block.section_type for block in blocks)
    entity_count = sum(len(values) for values in entities.values())

    return DocumentQualityReport(
        paragraph_score=paragraph_score,
        heading_score=heading_score,
        citation_cleanup_score=citation_score,
        footer_removal_score=footer_score,
        ocr_cleanup_score=ocr_score,
        section_segmentation_score=segmentation_score,
        coastal_entity_score=entity_score,
        final_quality=final_quality,
        section_counts=dict(section_counts),
        entity_count=entity_count,
    )
