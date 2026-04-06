"""
Layout-aware paragraph reconstruction for multi-column PDFs.

Repairs broken paragraphs at page boundaries, merges soft line breaks,
and preserves legal enumerations, headings, and judicial decision blocks.
"""

from __future__ import annotations

import re


_DANGLING_TAIL_RE = re.compile(
    r"(?i)\b(y|e|o|u|que|de|del|la|el|los|las|en|con|por|para|su|sus"
    r"|una|un|al|como|sin|ni|sobre|bajo|ante|entre|desde|hasta"
    r"|dicha|dicho|dichas|dichos|cuyo|cuya|cuyos|cuyas"
    r"|esta|este|estos|estas|aquel|aquella|todo|toda|cada"
    r"|ser|siendo|ha|han|fue|ser[aá]|deber[aá]|podr[aá])\s*$"
)


# ---------------------------------------------------------------------------
# Line-level helpers
# ---------------------------------------------------------------------------


def is_legal_enumeration(line: str) -> bool:
    """Return True if *line* starts a legal enumeration."""
    patterns = [
        r"^\d{1,3}\.\s",
        r"^[a-z]\)\s",
        r"^[ivxIVX]+\.\s",
        r"^[A-Z]\.\s",
        r"^\([a-z]\)\s",
        r"^\(\d+\)\s",
        r"^(?:PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO)[\.:]\s*",
    ]
    return any(re.match(p, line) for p in patterns)


def is_decision_block_start(line: str) -> bool:
    """Return True if *line* opens a judicial decision block."""
    decision_starters = [
        r"(?i)^RESUELVE\b",
        r"(?i)^FALLA\b",
        r"(?i)^DECIDE\b",
        r"(?i)^SE RESUELVE\b",
        r"(?i)^POR LO EXPUESTO\b",
        r"(?i)^EN MÉRITO DE LO EXPUESTO\b",
        r"(?i)^EN MERITO DE LO EXPUESTO\b",
    ]
    return any(re.match(p, line) for p in decision_starters)


def _should_merge_lines(current: str, next_line: str) -> bool:
    """Return True if two consecutive lines form a broken paragraph."""
    if not current or not next_line:
        return False
    if next_line.startswith(("#", "-", "*", "•")):
        return False
    if is_legal_enumeration(next_line) or is_decision_block_start(next_line):
        return False
    if current.rstrip()[-1:] in ".;:!?":
        return False

    last_char = current.rstrip()[-1:] if current.rstrip() else ""
    first_char = next_line[0] if next_line else ""
    return last_char not in ".;:!?\"')" and first_char.islower()


def _should_merge_paragraphs(current: str, next_para: str) -> bool:
    """Return True if two paragraphs split by a page break should be merged."""
    if not current or not next_para:
        return False
    if current.startswith("#") or next_para.startswith("#"):
        return False
    if re.match(r"^- \?", next_para):
        return False
    if re.match(r"^[*\-]\s+[A-ZÁÉÍÓÚÜÑ]", next_para):
        return False
    if len(next_para) > 1 and next_para[0].isdigit() and next_para[1] in ".)":
        return False

    last_char = current[-1]
    first_char = next_para[0]

    tail = current[-3:] if len(current) >= 3 else current
    if re.search(r"[.;:?!]['\u2019\u201D\"]\s*$", tail):
        return False

    ends_without_terminator = last_char not in ".;:?!\"')»"
    next_starts_lower = first_char.islower()

    if ends_without_terminator and next_starts_lower:
        return True
    if re.match(r"^-\s+[a-záéíóúüñ]", next_para) and ends_without_terminator:
        return True
    if _DANGLING_TAIL_RE.search(current):
        return True
    if last_char == "," and next_starts_lower:
        return True

    return False


# ---------------------------------------------------------------------------
# Public repair functions
# ---------------------------------------------------------------------------


def repair_layout_breaks(md_text: str) -> str:
    """
    Repair layout breaks from multi-column PDFs and page boundaries.

    Merges soft line breaks while preserving headings, legal enumerations,
    bullet points, and judicial decision block starters.
    """
    lines = md_text.splitlines()
    result: list[str] = []
    i = 0

    while i < len(lines):
        current = lines[i]
        stripped = current.strip()

        if not stripped:
            result.append(current)
            i += 1
            continue

        if (
            stripped.startswith("#")
            or is_legal_enumeration(stripped)
            or stripped.startswith(("-", "*", "•"))
            or is_decision_block_start(stripped)
        ):
            result.append(current)
            i += 1
            continue

        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if _should_merge_lines(stripped, next_line):
                result.append(stripped.rstrip() + " " + next_line.lstrip())
                i += 2
                continue

        result.append(current)
        i += 1

    return "\n".join(result)


def reconstruct_paragraphs(text: str) -> str:
    """Reconstruct paragraphs broken by page splits.

    Runs two sub-passes:
    1. Rejoin hyphenated word breaks.
    2. Merge paragraph pairs split across page boundaries (up to 3 iterations
       so chains A→B→C are joined progressively).
    """
    text = re.sub(
        r"([A-Za-záéíóúüñÁÉÍÓÚÜÑ])-\n([a-záéíóúüñ])",
        r"\1\2",
        text,
    )

    for _pass in range(3):
        paragraphs = text.split("\n\n")
        result: list[str] = []
        merged_any = False
        i = 0

        while i < len(paragraphs):
            current = paragraphs[i]
            stripped_current = current.strip()

            if not stripped_current:
                i += 1
                continue

            j = i + 1
            while j < len(paragraphs) and not paragraphs[j].strip():
                j += 1

            if j < len(paragraphs):
                stripped_next = paragraphs[j].strip()
                if _should_merge_paragraphs(stripped_current, stripped_next):
                    result.append(stripped_current + " " + stripped_next)
                    merged_any = True
                    i = j + 1
                    continue

            result.append(current)
            i += 1

        text = "\n\n".join(result)
        if not merged_any:
            break

    return text
