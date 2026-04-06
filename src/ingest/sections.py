# src/ingest/sections.py

from __future__ import annotations

import re
import unicodedata
from typing import Any

from langchain_core.documents import Document

# ---------------------------------------------------------------------------
# Canonical section names
# ---------------------------------------------------------------------------

SECTION_NAMES: dict[int, str] = {
    1: "Contexto del caso",
    2: "Desarrollo procesal",
    3: "Análisis del tribunal",
    4: "Decisión",
}

# ---------------------------------------------------------------------------
# Section keyword variants (normalised: no accents, lowercase, no punctuation)
# Each entry is checked as an exact match OR as a substring of the heading.
# ---------------------------------------------------------------------------

SECTION_VARIANTS: dict[int, list[str]] = {
    1: [
        "antecedentes",
        "sintesis del caso",
        "resumen de la demanda",
        "petitum",
        "causa petendi",
    ],
    2: [
        "contestacion de la demanda",
        "actuacion procesal",
        "actuaciones posteriores al fallo",
        "tramite de la accion",
        "tramite de la segunda instancia",
        "tramite de segunda instancia",
        "sentencia de primera instancia",
        "fallo de primera instancia",
        "el recurso de apelacion",
        "recurso de apelacion",
        "alegatos de conclusion",
        "trámite de la accion",
    ],
    3: [
        "consideraciones de la sala",
        "consideraciones del tribunal",
        "consideraciones",
    ],
    4: [
        "conclusiones",
        "decision",
        "falla",
        "resuelve",
    ],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LEADING_ENUM = re.compile(
    r"""
    ^                           # start of string
    (?:
        [IVXLCDM]+              # Roman numerals (I, V, X, L, C, D, M)
        |
        \d+(?:\.\d+)*           # Arabic numbers, possibly with dots (1, 1.2, 1.2.3)
    )
    (?=[.):\-\s]|$)             # must be followed by a separator or end-of-string
                                # (prevents stripping letters that are part of a real word,
                                # e.g. "C" in "CONSIDERACIONES")
    [.):\-\s]*                  # consume the separator chars
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _strip_accents(text: str) -> str:
    """Convert accented characters to their ASCII base (e.g. á → a)."""
    return "".join(
        c
        for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def normalize_heading(text: str) -> str:
    """
    Return a canonical form of a heading used for section classification:
    - Strip leading enumeration (Roman / Arabic numbers with separators)
    - Remove punctuation except spaces
    - Lowercase
    - Strip accents
    - Collapse whitespace
    """
    text = text.strip()
    text = _LEADING_ENUM.sub("", text)
    text = _strip_accents(text)
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def classify_heading(heading: str) -> int | None:
    """
    Return the section number (1–4) for *heading*, or None if unrecognised.

    Matching strategy: the normalised heading must *start with* one of the
    known variants (allowing for a small trailing suffix).  Longer variants
    are checked before shorter ones so specifics win over generals
    (e.g. "el recurso de apelacion" before "recurso de apelacion").

    Using startswith rather than arbitrary substring prevents false positives
    from long paragraph titles that happen to contain section keywords
    (e.g. "puntualmente las conclusiones del estudio fueron").
    """
    norm = normalize_heading(heading)
    if not norm:
        return None

    for section_num in (1, 2, 3, 4):
        # Sort variants by length desc so longer (more specific) win first
        variants = sorted(SECTION_VARIANTS[section_num], key=len, reverse=True)
        for variant in variants:
            # Accept if the normalised heading starts with the variant
            # (covers "conclusiones", "falla", "consideraciones del tribunal", etc.)
            if norm.startswith(variant):
                return section_num

    return None


# ---------------------------------------------------------------------------
# Core splitting function
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^## (.+)$", re.MULTILINE)


def split_by_sections(doc: Document) -> list[Document]:
    """
    Split a normalised Document into exactly 4 Documents, one per section.

    Algorithm
    ---------
    1. Split the full text into blocks on ``## `` headings.
    2. For each block, classify its heading; if recognised update the active
       section, otherwise inherit the previous one.
    3. Preamble text before the first recognised heading goes into section 1.
    4. Each output Document inherits the parent metadata and receives extra
       fields: ``section_index``, ``section_name``, ``section_heading``.

    Empty sections produce a Document with ``page_content = ""``.
    """
    text: str = doc.page_content
    base_meta: dict[str, Any] = dict(doc.metadata)

    # Accumulate raw text per section
    section_chunks: dict[int, list[str]] = {i: [] for i in range(1, 5)}
    # Track the first heading that triggered each section
    section_first_heading: dict[int, str] = {}

    # Split into blocks: each block starts at a '## ' heading
    # Positions of all '## ' headings
    matches = list(_HEADING_RE.finditer(text))

    if not matches:
        # No headings at all – dump everything into section 1
        section_chunks[1].append(text)
    else:
        # Text before the very first heading (may be empty)
        preamble = text[: matches[0].start()].strip()

        active_section: int = 1  # default until first recognised heading
        preamble_assigned = False

        for idx, match in enumerate(matches):
            heading_text = match.group(1)
            block_start = match.start()
            block_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            block_body = text[block_start:block_end]  # includes the '## heading' line

            classified = classify_heading(heading_text)

            # Handle "split headings": some documents write the Roman/Arabic
            # numeral on the '## ' line and the actual section name on the
            # very next non-blank line (e.g. "## IV.\nCONSIDERACIONES DEL TRIBUNAL").
            if classified is None and not normalize_heading(heading_text):
                body_lines = block_body.split("\n")
                # Look for the first non-empty line after the '## heading' line
                first_content = next(
                    (ln.strip() for ln in body_lines[1:] if ln.strip() and not ln.startswith("#")),
                    "",
                )
                if first_content:
                    classified = classify_heading(first_content)
                    if classified is not None:
                        # Use the continuation line as the canonical heading text
                        heading_text = first_content

            if classified is not None:
                # Before switching section, flush preamble into previous active
                if not preamble_assigned and preamble:
                    section_chunks[active_section].append(preamble)
                    preamble_assigned = True

                active_section = classified
                if active_section not in section_first_heading:
                    section_first_heading[active_section] = heading_text.strip()

            else:
                # Unrecognised heading → inherits active section.
                # Flush preamble on first block regardless.
                if not preamble_assigned and preamble:
                    section_chunks[active_section].append(preamble)
                    preamble_assigned = True

            section_chunks[active_section].append(block_body)

        # If no heading was ever recognised the preamble is still unflushed
        if not preamble_assigned and preamble:
            section_chunks[1].append(preamble)

    # Build one Document per section
    result: list[Document] = []
    for section_idx in range(1, 5):
        content = "\n\n".join(chunk.strip() for chunk in section_chunks[section_idx] if chunk.strip())
        meta = {
            **base_meta,
            "section_index": section_idx,
            "section_name": SECTION_NAMES[section_idx],
            "section_heading": section_first_heading.get(section_idx, ""),
        }
        result.append(Document(page_content=content, metadata=meta))

    return result
