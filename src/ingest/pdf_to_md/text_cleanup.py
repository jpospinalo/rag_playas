"""
Text normalization helpers: OCR artifact correction, noise removal,
footnote-number stripping, heading/body splitting, and final markdown cleanup.
"""

from __future__ import annotations

import re
from collections import Counter

from .config import FOOTNOTE_LEGAL_CONTEXT, MD_STRUCTURE_RE, MIN_BLOCK_REPEATS, NOISE_CHAR_RATIO, OCR_CORRECTIONS


# ---------------------------------------------------------------------------
# OCR character correction
# ---------------------------------------------------------------------------


def fix_ocr_chars(text: str) -> str:
    """Fix common OCR artifacts in Spanish legal documents.

    Image markdown tokens (``![alt](path)``) are skipped to avoid mangling
    image references.
    """
    img_token_re = re.compile(r"(!\[[^\]]*\]\([^)]+\))")
    parts = img_token_re.split(text)

    result_parts: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            result_parts.append(part)
        else:
            for pattern, replacement in OCR_CORRECTIONS:
                part = pattern.sub(replacement, part)
            result_parts.append(part)

    return "".join(result_parts)


# ---------------------------------------------------------------------------
# Noise line removal
# ---------------------------------------------------------------------------

_INSTITUTIONAL_NOISE_RE = re.compile(
    r"^("
    r"\d{7,}\s*\S{0,30}$"
    r"|[A-Za-z]*@\S+$"
    r"|[XxYy][\s@]?\S{0,30}$"
    r"|(?:YouTube|YeuTube|Facebook|Instagram|Twitter)\b.*$"
    r"|[a-z]\d{2}[a-z]\w{0,30}$"
    r")",
    re.IGNORECASE,
)


def remove_noisy_lines(text: str, noise_ratio: float = NOISE_CHAR_RATIO) -> str:
    """Remove lines with high ratio of non-linguistic characters and
    institutional noise (phone numbers, social handles)."""
    cleaned: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue
        if MD_STRUCTURE_RE.match(stripped):
            cleaned.append(line)
            continue
        if _INSTITUTIONAL_NOISE_RE.match(stripped):
            continue
        non_linguistic = sum(1 for c in stripped if not c.isalnum() and not c.isspace())
        if non_linguistic / len(stripped) < noise_ratio:
            cleaned.append(line)
    return "\n".join(cleaned)


# ---------------------------------------------------------------------------
# Frontmatter / pre-heading noise
# ---------------------------------------------------------------------------


def strip_frontmatter_noise(text: str) -> str:
    """Remove OCR noise lines that precede the first real heading.

    The first pages of Colombian tribunal PDFs often contain institutional
    banners, seals, phone numbers, and social-media handles.  Everything
    before the first ``## `` heading that does NOT look like meaningful
    legal prose is discarded.
    """
    lines = text.splitlines()
    first_heading_idx = next(
        (idx for idx, line in enumerate(lines) if line.strip().startswith("## ")),
        None,
    )

    if first_heading_idx is None or first_heading_idx < 2:
        return text

    _junk_re = re.compile(
        r"^("
        r"\d{7,}"
        r"|[A-Z@#·\s\-\.\d]{3,50}$"
        r"|.{0,5}$"
        r"|.*[@#].*"
        r")",
        re.MULTILINE,
    )

    kept_preamble: list[str] = []
    for line in lines[:first_heading_idx]:
        stripped = line.strip()
        if not stripped:
            kept_preamble.append(line)
            continue
        if _junk_re.match(stripped):
            continue
        alpha = sum(1 for c in stripped if c.isalpha())
        if len(stripped) > 0 and alpha / len(stripped) < 0.5:
            continue
        kept_preamble.append(line)

    return "\n".join(kept_preamble + lines[first_heading_idx:])


# ---------------------------------------------------------------------------
# Figure legend cluster removal
# ---------------------------------------------------------------------------


def remove_figure_legend_clusters(text: str) -> str:
    """Remove clusters of short lines that are map/figure legend artifacts.

    When Docling extracts text from embedded maps or diagrams it produces
    runs of 3+ consecutive short lines (< 35 chars) with no linguistic
    connectors — just place names, units, and legend labels.
    """
    _CONNECTOR_RE = re.compile(
        r"(?i)\b(que|para|por|con|sin|como|según|entre|sobre|bajo"
        r"|durante|mediante|desde|hasta|siendo|puede|debe|tiene"
        r"|está|fue|han|será|son|del|los|las|una|uno|este|esta)\b"
    )
    paragraphs = text.split("\n\n")
    result: list[str] = []

    for para in paragraphs:
        lines = [line.strip() for line in para.splitlines() if line.strip()]
        if len(lines) < 3:
            result.append(para)
            continue

        short_count = sum(1 for line in lines if len(line) < 35)
        if short_count < 3 or short_count / len(lines) < 0.6:
            result.append(para)
            continue

        joined = " ".join(lines)
        if _CONNECTOR_RE.search(joined):
            result.append(para)

    return "\n\n".join(result)


# ---------------------------------------------------------------------------
# Footnote number stripping
# ---------------------------------------------------------------------------


def remove_footnote_numbers(text: str) -> str:
    """Remove footnote markers from the text.

    Handles:
    1. Glued markers: ``jurisdicción14`` → ``jurisdicción``
    2. Spaced markers: ``contestó 6`` → ``contestó``
    3. Closing-paren/quote + marker: ``INVEMAR) 13`` → ``INVEMAR)``
    4. Year + trailing digit: ``20228`` → ``2022``
    5. Year + spaced marker: ``2021 32 ,`` → ``2021,``
    6. Hyphenated code + marker: ``CPT-CAM-012-21 34`` → ``CPT-CAM-012-21``

    Legal context (ley, artículo, etc.) prevents stripping.
    """
    _CITATION_WORD = re.compile(
        r"(?i)^(ley|artículo|articulo|decreto|numeral|inciso|parágrafo"
        r"|paragrafo|literal|ordinal|resolución|resolucion)$"
    )

    # Pass 1: glued
    word_digit_glued = re.compile(
        r"([A-Za-záéíóúüñÁÉÍÓÚÜÑ]{2,})(\d{1,2})\b(?!\d)",
        re.UNICODE,
    )

    def _replace_glued(m: re.Match[str]) -> str:
        word_part = m.group(1)
        preceding = text[max(0, m.start() - 40) : m.start()]
        if FOOTNOTE_LEGAL_CONTEXT.search(preceding) or _CITATION_WORD.match(word_part):
            return m.group(0)
        return word_part

    text = word_digit_glued.sub(_replace_glued, text)

    # Pass 2: spaced
    word_space_digit = re.compile(
        r"([A-Za-záéíóúüñÁÉÍÓÚÜÑ]{2,})"
        r"(\s+)"
        r"(\d{1,2})"
        r"(?=\s|[.,;:!?\)\]\"\']|$)"
    )

    def _replace_spaced(m: re.Match[str]) -> str:
        word_part = m.group(1)
        digit = m.group(3)
        preceding = text[max(0, m.start() - 40) : m.start()]
        if FOOTNOTE_LEGAL_CONTEXT.search(preceding) or _CITATION_WORD.match(word_part):
            return m.group(0)
        if int(digit) > 55:
            return m.group(0)
        return word_part

    text = word_space_digit.sub(_replace_spaced, text)

    # Pass 3: closing-paren/quote + spaced footnote
    paren_space_fn = re.compile(
        r"([)\]\u2019\u201D'\"])"
        r"(\s+)"
        r"(\d{1,2})"
        r"(?=\s|[.,;:!?\)\]]|$)"
    )
    text = paren_space_fn.sub(r"\1", text)

    # Pass 4: year + trailing digit
    year_digit = re.compile(r"\b((?:1[89]\d\d|20\d\d))(\d)\b(?!\d)")
    text = year_digit.sub(r"\1", text)

    # Pass 5: year + spaced footnote
    year_space_fn = re.compile(
        r"(\b(?:1[89]\d\d|20\d\d))"
        r"(\s+)"
        r"(\d{1,2})"
        r"(?=\s*[.,;:!?\)\]]|\s+[a-záéíóúüñ]|\s*$)"
    )
    text = year_space_fn.sub(r"\1", text)

    # Pass 6: hyphenated code + spaced footnote
    code_space_fn = re.compile(
        r"(\b[A-Z][\w-]*-\d{2,4})"
        r"(\s+)"
        r"(\d{1,2})"
        r"(?=\s|[.,;:!?\)\]]|$)"
    )
    text = code_space_fn.sub(r"\1", text)

    return text


# ---------------------------------------------------------------------------
# Repeated block deduplication
# ---------------------------------------------------------------------------


def remove_repeated_blocks(text: str, min_occurrences: int = MIN_BLOCK_REPEATS) -> str:
    """Detect and remove repeated text blocks (headers/footers)."""
    paragraphs = text.split("\n\n")

    def _normalize(block: str) -> str:
        s = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", block)
        return s.strip()

    counts: Counter[str] = Counter(_normalize(p) for p in paragraphs if _normalize(p))
    repeated = {norm for norm, count in counts.items() if count >= min_occurrences}

    return "\n\n".join(p for p in paragraphs if _normalize(p) not in repeated)


# ---------------------------------------------------------------------------
# Heading / body split and final markdown cleanup
# ---------------------------------------------------------------------------

_HEADING_BODY_RE = re.compile(
    r"^(#{1,6}\s+"
    r"(?:"
    r"[IVXivx]+\."
    r"|"
    r"\d+(?:\.\d+)*\.?"
    r")?"
    r"\s*"
    r"[A-ZÁÉÍÓÚÜÑ][^.]*?"
    r"\.)"
    r"\s+"
    r"([A-ZÁÉÍÓÚÜÑ]"
    r"[A-Za-záéíóúüñÁÉÍÓÚÜÑ\s,()]{10,})"
)


def _find_next_paragraph_number(lines: list[str], start_idx: int) -> int | None:
    """Scan forward for the first line starting with a legal paragraph number."""
    for j in range(start_idx, min(start_idx + 15, len(lines))):
        m = re.match(r"^(\d{1,3})\.\s", lines[j])
        if m:
            return int(m.group(1))
    return None


def _maybe_prepend_number(body: str, lines: list[str], start_idx: int) -> str:
    """Prepend the missing first paragraph number when Docling absorbed it
    into the heading section number."""
    next_num = _find_next_paragraph_number(lines, start_idx)
    if next_num is not None and next_num >= 2:
        expected = next_num - 1
        if not re.match(r"^\d+\.\s", body):
            body = f"{expected}. {body}"
    return body


def split_heading_body(text: str) -> str:
    r"""Separate heading titles from body text that Docling fused onto the
    same ``## `` line.

    Example input:  ``## 1.1. Posición de la parte demandante. En síntesis, ...``
    Example output: ``## 1.1. Posición de la parte demandante.\n1. En síntesis, ...``
    """
    lines = text.splitlines()
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _HEADING_BODY_RE.match(line)
        if m:
            result.append(m.group(1))
            body = m.group(2) + line[m.end() :]
            body = _maybe_prepend_number(body, lines, i + 1)
            result.append(body)
        else:
            result.append(line)
        i += 1
    return "\n".join(result)


def clean_markdown(text: str) -> str:
    """Final structural normalization of markdown."""
    text = split_heading_body(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"([^\n])\n(#{1,6}\s)", r"\1\n\n\2", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text.strip() + "\n"
