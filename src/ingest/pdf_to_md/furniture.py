"""
Header/footer detection by page frequency analysis.

Identifies lines that appear repeatedly across pages (page furniture)
and removes them from the processed markdown.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from .config import REPEATED_FURNITURE_THRESHOLD

logger = logging.getLogger(__name__)


def _normalize_furniture_line(line: str) -> str:
    """Normalize a line for furniture comparison (fuzzy matching)."""
    normalized = re.sub(r"\b(pág\.?|página|page)\s*\d+\b", "", line, flags=re.IGNORECASE)
    normalized = re.sub(r"\b\d{1,4}\s*$", "", normalized)
    normalized = re.sub(r"^\s*\d{1,4}\s+", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return normalized


def detect_repeated_page_furniture(pages: list[str]) -> set[str]:
    """
    Detect repeated header/footer lines using page frequency analysis.

    Analyzes the first and last 2 lines of each page and marks lines
    appearing in >= 60 % of pages as furniture.
    """
    if len(pages) < 3:
        return set()

    line_counts: Counter[str] = Counter()

    for page in pages:
        page_lines = [line.strip() for line in page.splitlines() if line.strip()]
        if len(page_lines) < 4:
            continue

        for line in page_lines[:2]:
            normalized = _normalize_furniture_line(line)
            if normalized and 3 < len(normalized) < 150:
                line_counts[normalized] += 1

        for line in page_lines[-2:]:
            normalized = _normalize_furniture_line(line)
            if normalized and 3 < len(normalized) < 150:
                line_counts[normalized] += 1

    threshold = len(pages) * REPEATED_FURNITURE_THRESHOLD
    repeated = {line for line, count in line_counts.items() if count >= threshold}

    logger.debug("Detected %d repeated furniture lines across %d pages", len(repeated), len(pages))
    return repeated


def remove_page_furniture(md_text: str, repeated_lines: set[str]) -> str:
    """Remove identified repeated header/footer lines from text."""
    if not repeated_lines:
        return md_text

    lines = md_text.splitlines()
    cleaned = [line for line in lines if _normalize_furniture_line(line) not in repeated_lines]
    return "\n".join(cleaned)


def split_into_pages(md_text: str) -> list[str]:
    """
    Split markdown text into approximate pages.

    Tries explicit page markers first; falls back to paragraph-based
    heuristics (~3 000 chars per page).
    """
    page_pattern = re.compile(r"\n(?=(?:pág\.?\s*\d+|página\s*\d+|---+\s*\d+))", re.IGNORECASE)
    pages = page_pattern.split(md_text)

    if len(pages) >= 3:
        return pages

    paragraphs = md_text.split("\n\n")
    pages = []
    current_page: list[str] = []
    current_len = 0

    for para in paragraphs:
        current_page.append(para)
        current_len += len(para)

        if current_len > 3000:
            pages.append("\n\n".join(current_page))
            current_page = []
            current_len = 0

    if current_page:
        pages.append("\n\n".join(current_page))

    return pages
