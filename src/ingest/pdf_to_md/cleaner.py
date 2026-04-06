"""
Adaptive cleanup pipeline orchestrator.

Applies a fixed sequence of cleanup steps to legal-document markdown,
delegating each step to the appropriate sub-module.
"""

from __future__ import annotations

from pathlib import Path

from .furniture import detect_repeated_page_furniture, remove_page_furniture
from .images import filter_images, relativize_image_refs
from .layout import reconstruct_paragraphs, repair_layout_breaks
from .models import LegalDocumentProfile
from .references import remove_footnote_citation_blocks, remove_internal_references
from .text_cleanup import (
    clean_markdown,
    fix_ocr_chars,
    remove_figure_legend_clusters,
    remove_footnote_numbers,
    remove_noisy_lines,
    remove_repeated_blocks,
    strip_frontmatter_noise,
)


def adaptive_cleanup(
    md_text: str,
    profile: LegalDocumentProfile,
    md_path: Path | None = None,
) -> str:
    """Apply the full cleanup pipeline to legal-document markdown.

    Pipeline steps (always executed in order):

    1.  ``strip_frontmatter_noise``         — remove OCR junk before first heading
    2.  ``fix_ocr_chars``                   — correct OCR character artifacts
    3.  ``remove_noisy_lines``              — drop high-noise lines
    4.  ``repair_layout_breaks``            — merge broken lines from multi-column
    5.  ``remove_internal_references``      — footnote bodies & page refs
    6.  ``remove_footnote_citation_blocks`` — map/figure label clusters
    7.  ``remove_figure_legend_clusters``   — legend artifact clusters
    8.  ``reconstruct_paragraphs``          — rejoin split paragraphs
    9.  ``remove_footnote_numbers``         — strip footnote markers from words
    10. ``remove_repeated_blocks``          — deduplicate headers/footers
    11. ``filter_images``                   — filter irrelevant images (if md_path given)
    12. ``clean_markdown``                  — final structural normalization
    """
    md_text = strip_frontmatter_noise(md_text)
    md_text = fix_ocr_chars(md_text)
    md_text = remove_noisy_lines(md_text)
    md_text = repair_layout_breaks(md_text)
    md_text = remove_internal_references(md_text)
    md_text = remove_footnote_citation_blocks(md_text)
    md_text = remove_figure_legend_clusters(md_text)
    md_text = reconstruct_paragraphs(md_text)
    md_text = remove_footnote_numbers(md_text)
    md_text = remove_repeated_blocks(md_text)

    if md_path is not None:
        md_text = filter_images(md_text, md_path)

    md_text = clean_markdown(md_text)

    return md_text
