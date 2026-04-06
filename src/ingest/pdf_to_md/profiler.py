"""
Document profiling stage: analyzes raw markdown to build a
LegalDocumentProfile used by downstream adaptive processing.
"""

from __future__ import annotations

import re
from collections import Counter

from .config import COASTAL_PATTERN, OCR_NOISE_THRESHOLD, REPEATED_FURNITURE_THRESHOLD
from .models import LegalDocumentProfile

_LEGAL_CITATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(ley|decreto|artículo|articulo|sentencia|expediente)\s*\d"),
    re.compile(r"(?i)\b(c\.p\.|c\.c\.|c\.p\.c\.|c\.g\.p\.)\b"),
    re.compile(r"(?i)\bcorte\s+(constitucional|suprema)\b"),
    re.compile(r"(?i)\bconsejo\s+de\s+estado\b"),
    re.compile(r"(?i)\b[TSC]-\d{3,}\b"),
    re.compile(r"(?i)\bresolución\s*n?[°º]?\s*\d"),
]

_OCR_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[^\w\s]{3,}"),
    re.compile(r"\d[a-z]\d"),
    re.compile(r"[a-z]\d[a-z]"),
    re.compile(r"[\x00-\x1f]"),
    re.compile(r"[ﬁﬂ]"),
]

_FOOTNOTE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*\d{1,2}\s+[A-Z]"),
    re.compile(r"^\s*\[\d+\]"),
    re.compile(r"^\s*\(\d+\)"),
    re.compile(r"(?i)^\s*\d{1,2}\s+(ver|véase|cf\.|vid\.)\b"),
]


def _count_pattern_matches(text: str, patterns: list[re.Pattern[str]]) -> int:
    """Count total matches of multiple patterns in text."""
    return sum(len(p.findall(text)) for p in patterns)


def _detect_multi_column(lines: list[str]) -> bool:
    """Heuristic detection of multi-column layout based on line-length variance."""
    if len(lines) < 10:
        return False

    lengths = [len(line.strip()) for line in lines if line.strip()]
    if len(lengths) < 10:
        return False

    avg_len = sum(lengths) / len(lengths)
    short_lines = sum(1 for length in lengths if length < avg_len * 0.4)
    return short_lines / len(lengths) > 0.35


def _detect_heading_consistency(text: str) -> float:
    """Measure consistency of markdown heading usage (0–1)."""
    lines = text.splitlines()
    headings = [line for line in lines if line.strip().startswith("#")]

    if len(headings) < 2:
        return 0.5

    levels = [len(h.split()[0]) if h.split() else 0 for h in headings]
    jumps = sum(1 for i in range(1, len(levels)) if abs(levels[i] - levels[i - 1]) > 1)
    return max(0.0, 1.0 - (jumps / len(headings)))


def _estimate_repeated_furniture(lines: list[str], position: str = "start") -> bool:
    """Quick estimate of whether repeated headers/footers are likely present."""
    if len(lines) < 20:
        return False

    sample_size = min(50, len(lines) // 4)

    if position == "start":
        samples = [
            lines[i].strip().lower()
            for i in range(0, len(lines), max(1, len(lines) // sample_size))
            if i < len(lines)
        ][:sample_size]
    else:
        samples = [lines[-(i + 1)].strip().lower() for i in range(0, min(sample_size, len(lines)))]

    if not samples:
        return False

    short_samples = [s for s in samples if 5 < len(s) < 100]
    if not short_samples:
        return False

    counts = Counter(short_samples)
    most_common_count = counts.most_common(1)[0][1] if counts else 0
    return most_common_count >= 3


def profile_legal_document(md_text: str) -> LegalDocumentProfile:
    """
    Analyze a legal document to build a profile for adaptive processing.

    Detects text density, repeated furniture, legal citation density, OCR
    corruption score, multi-column layout, heading consistency, footnote
    density, and coastal/beach-law semantic density.
    """
    lines = md_text.splitlines()
    total_chars = len(md_text)
    total_words = len(md_text.split())

    if total_chars == 0:
        return LegalDocumentProfile()

    legal_matches = _count_pattern_matches(md_text, _LEGAL_CITATION_PATTERNS)
    legal_density = legal_matches / max(1, total_words / 100)

    noise_matches = _count_pattern_matches(md_text, _OCR_NOISE_PATTERNS)
    ocr_noise_score = noise_matches / max(1, total_chars / 1000)

    footnote_matches = _count_pattern_matches(md_text, _FOOTNOTE_PATTERNS)
    footnote_density = footnote_matches / max(1, len(lines) / 10)

    coastal_matches = len(COASTAL_PATTERN.findall(md_text))
    coastal_density = coastal_matches / max(1, total_words / 100)

    multi_column = _detect_multi_column(lines)
    heading_consistency = _detect_heading_consistency(md_text)

    page_markers = len(re.findall(r"(?i)(pág\.?\s*\d+|página\s*\d+|\bpage\s*\d+)", md_text))
    total_pages = max(1, page_markers)

    is_scanned = ocr_noise_score > OCR_NOISE_THRESHOLD * 2
    repeated_headers = _estimate_repeated_furniture(lines, position="start")
    repeated_footers = _estimate_repeated_furniture(lines, position="end")

    paragraphs = [p for p in md_text.split("\n\n") if p.strip()]

    return LegalDocumentProfile(
        is_scanned=is_scanned,
        repeated_headers=repeated_headers,
        repeated_footers=repeated_footers,
        multi_column=multi_column,
        legal_density=legal_density,
        ocr_noise_score=ocr_noise_score,
        footnote_density=footnote_density,
        coastal_semantic_density=coastal_density,
        heading_consistency=heading_consistency,
        total_pages=total_pages,
        total_paragraphs=len(paragraphs),
    )
