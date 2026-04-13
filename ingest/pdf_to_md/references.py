"""
Heuristic scoring and removal of legal internal references,
footnote bodies, and citation metadata blocks.
"""

from __future__ import annotations

import re

from .config import INTERNAL_REF_SCORE_THRESHOLD

# ---------------------------------------------------------------------------
# Footnote citation block detection
# ---------------------------------------------------------------------------

_CITATION_ANCHOR_RE = re.compile(
    r"(?i)Radicaci[oó]n:\s*\d{2,}|"
    r"Referencia:\s*medio\s+de\s+control|"
    r"[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+\s+[A-ZÁÉÍÓÚÜÑ]"
    r"[a-záéíóúüñ]+\.\s+Bogot[aá]"
)

_CITATION_FRAGMENT_RE = re.compile(
    r"(?i)^("
    r"\d{5}-\d+\.\s*Demandante:|"
    r"General\s+de\b|"
    r"Delegad[oa]\s+para\b|"
    r"la\s+Naci[oó]n$|"
    r"Procuradur[ií]a$|"
    r"Nacional\s+de\s+Licencias\b|"
    r"-$|"
    r"Ambientales\s+y\s+Agrarios|"
    r"Asuntos$|"
    r"Naci[oó]n\s*-\s*Ministerio\b|"
    r".*-\s*ANLA\b|"
    r".*-\s*otros\.\s*$"
    r")"
)


def _score_internal_reference(line: str) -> int:
    """Calculate internal-reference score for a line.

    Lines scoring >= INTERNAL_REF_SCORE_THRESHOLD are considered internal
    references and will be removed from the document.
    """
    score = 0
    stripped = line.strip()
    line_lower = stripped.lower()

    # === High confidence (+3) ===
    if re.search(r"(?i)^\s*\d{0,2}\s*ver\s+p[aá]gs?\.?\s*\d", line):
        score += 3
    if re.search(r"(?i)^\s*\d{0,2}\s*ver\s+pdf\b", line):
        score += 3
    if re.search(r"(?i)\bver\s+pdf\s*:?\s*\d+\b", line):
        score += 3
    if re.search(r"(?i)\bver\s+folio\b", line):
        score += 3

    if re.match(r"^\s*\d{1,2}\s{2,}[A-ZÁÉÍÓÚÜÑ]", stripped):
        score += 3
    if re.match(r"^\s*\d{1,2}\s{2,}[a-záéíóúüñ]", stripped):
        score += 3

    # === Medium confidence (+2) ===
    if re.search(r"(?i)^\s*folio[s]?\s+\d+", line):
        score += 2
    if re.search(r"(?i)^\s*cuaderno\s+\d+", line):
        score += 2
    if re.search(r"(?i)\barchivo\s+\S+\.pdf\b", line):
        score += 2
    if re.search(r"(?i)^\s*expediente\s+n[°º]?\s*\d", line):
        score += 2
    if re.search(r"https?://", line):
        score += 2
    if re.search(r"(?i)onedrive|sharepoint|drive\.google", line):
        score += 2
    if re.search(r"(?i)\bpdf\s+\d{2}\s+del\s+expediente\b", line):
        score += 2
    if re.search(r"(?i)\bexpediente\s+electrónico\s+judicial\b", line):
        score += 2

    # Specific footnote phrase patterns (+3)
    _HIGH_SCORE_PHRASES = [
        (r"(?i)^\s*\d{1,2}\s+en adelante\b", 3),
        (r"(?i)^\s*\d{1,2}\s+al respecto\b", 3),
        (r"(?i)^\s*\d{1,2}\s+m\.p\.\b", 3),
        (
            r"(?i)^\s*\d{1,2}\s+(corte constitucional|consejo de estado"
            r"|sección primera|sala plena|sala de lo contencioso)\b",
            3,
        ),
        (r"(?i)^\s*\d{1,2}\s+en cumplimiento\b", 3),
        (r"(?i)^\s*\d{1,2}\s+vale la pena\b", 3),
        (r"(?i)^\s*\d{1,2}\s+presentación de la demanda\b", 3),
        (r"(?i)^\s*\d{1,2}\s+[A-Za-z]{1,3}-\d{3,}\b", 3),
        (r"(?i)^\s*\d{1,2}\s+por (el|la|lo) cual\b", 3),
    ]
    for pattern, pts in _HIGH_SCORE_PHRASES:
        if re.search(pattern, line):
            score += pts

    if re.match(r"^\s*\d{1,2}\s*['\u2018\u2019\u201C\u201D]?\s*$", stripped):
        score += 3

    if re.match(
        r"(?i)^\s*\d{0,2}\s*(radicaci[oó]n|demandante|demandados?|ponente"
        r"|magistrad[oa]|secretari[oa])\s*:",
        stripped,
    ):
        if len(stripped) < 120:
            score += 3

    if re.match(r"(?i)^por\s+medio\s+del\s+cual\s+se\b", stripped):
        if len(stripped) < 120:
            score += 3

    # === Lower confidence (+1) ===
    if re.search(r"(?i)^\s*p[aá]g\.?\s*\d+\s*$", line):
        score += 1
    if re.search(r"(?i)^\s*ver\s+considerando\b", line):
        score += 1

    if len(line_lower) < 80 and score > 0:
        score += 1

    return score


def is_legal_internal_reference(line: str) -> bool:
    """Return True if *line* scores as an internal/footnote reference."""
    return _score_internal_reference(line) >= INTERNAL_REF_SCORE_THRESHOLD


def remove_internal_references(text: str) -> str:
    """Remove internal references using heuristic scoring."""
    text = re.sub(
        r"(?im)^\s*p[aá]g\.?\s*\d+\s+(?=[a-záéíóúüñ])",
        "",
        text,
    )
    lines = text.splitlines()
    cleaned = [line for line in lines if not is_legal_internal_reference(line)]
    return "\n".join(cleaned)


def remove_footnote_citation_blocks(text: str) -> str:
    """Remove multi-paragraph footnote citation blocks from cited decisions.

    These blocks contain the cited decision's metadata (Radicación, parties,
    judge name) spread across many short fragmented lines produced by
    multi-column OCR.
    """
    paragraphs = text.split("\n\n")
    to_remove: set[int] = set()

    for idx, para in enumerate(paragraphs):
        stripped = para.strip()
        if not stripped or not _CITATION_ANCHOR_RE.search(stripped):
            continue
        if stripped.startswith("#") or stripped.startswith("|"):
            continue

        to_remove.add(idx)
        for j in range(idx + 1, min(idx + 20, len(paragraphs))):
            frag = paragraphs[j].strip()
            if not frag:
                continue
            if frag.startswith("#") or frag.startswith("|"):
                break
            if re.match(r"^\d{1,3}\.\s", frag):
                break
            if _CITATION_FRAGMENT_RE.match(frag):
                to_remove.add(j)
            elif len(frag) < 70 and not re.match(r"^\d{1,3}\.\s", frag):
                to_remove.add(j)
            else:
                break

    if not to_remove:
        return text

    cleaned = [p for i, p in enumerate(paragraphs) if i not in to_remove]
    return "\n\n".join(cleaned)
