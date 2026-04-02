# src/ingest/pdf_to_md.py
"""
Production-grade adaptive legal PDF-to-Markdown pipeline specialized for
Spanish beach/coastal legal jurisprudence documents.

Features:
- Document profiling with adaptive cleanup selection
- Statistical header/footer detection by page frequency
- Heuristic scoring for legal internal references
- Layout-aware paragraph reconstruction
- Semantic legal section segmentation
- Coastal legal entity extraction
- Automated quality evaluation with JSON sidecar output
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import statistics
import time
import unicodedata
import warnings
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import unquote

from PIL import Image

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import ImageRefMode

warnings.filterwarnings("ignore", category=FutureWarning)

logging.getLogger("docling").setLevel(logging.WARNING)
logging.getLogger("rapidocr").setLevel(logging.WARNING)
logging.getLogger("onnxruntime").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Tuneable constants
# ------------------------------------------------------------------

IMAGE_RESOLUTION_SCALE = 2.0
MIN_IMAGE_PIXELS = 350
MIN_BLOCK_REPEATS = 2
NOISE_CHAR_RATIO = 0.45
IMAGE_LOW_VARIANCE = 100.0
IMAGE_CONTEXT_WINDOW = 300
IMAGE_REQUIRE_SEMANTIC_CONTEXT = True
IMAGE_MIN_AREA_KEEP_WITHOUT_CONTEXT = 250_000
IMAGE_FALLBACK_KEEP_ENABLED = True
IMAGE_FALLBACK_MAX_KEEP = 2
IMAGE_FALLBACK_MIN_AREA = 160_000

# Thresholds for document profiling
LEGAL_DENSITY_THRESHOLD = 0.15
FOOTNOTE_DENSITY_THRESHOLD = 0.10
OCR_NOISE_THRESHOLD = 0.05
REPEATED_FURNITURE_THRESHOLD = 0.60
COASTAL_DENSITY_THRESHOLD = 0.02

# Internal reference scoring threshold
INTERNAL_REF_SCORE_THRESHOLD = 3

# ------------------------------------------------------------------
# OCR correction table
# ------------------------------------------------------------------

_OCR_CORRECTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ci6nes\b"), "ciones"),
    (re.compile(r"ci6n\b"), "ción"),
    (re.compile(r"([A-Za-záéíóúüñÁÉÍÓÚÜÑ])6n\b"), r"\1ón"),
    (re.compile(r"([A-Za-záéíóúüñÁÉÍÓÚÜÑ])6s\b"), r"\1ós"),
    (re.compile(r"([a-záéíóúüñ])6([a-záéíóúüñ])"), r"\1ó\2"),
    # Additional common OCR errors in Spanish legal documents
    (re.compile(r"\b0([a-záéíóúüñ])"), r"o\1"),  # 0 -> o at word start
    (re.compile(r"([a-záéíóúüñ])0\b"), r"\1o"),  # 0 -> o at word end
    (re.compile(r"\bl([0O])s\b"), "los"),  # l0s, lOs -> los
    (re.compile(r"\bd([0O])s\b"), "dos"),  # d0s, dOs -> dos
    (re.compile(r"(?i)\bpr([0O])ceso\b"), "proceso"),
    (re.compile(r"(?i)\bc([0O])nsejo\b"), "consejo"),
]

# ------------------------------------------------------------------
# Markdown structure line detector
# ------------------------------------------------------------------

_MD_STRUCTURE_RE: re.Pattern[str] = re.compile(r"^\s*(#{1,6}\s|[-*|!]|\d+\.|---)")

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"

# ------------------------------------------------------------------
# Legal context patterns for footnote protection
# ------------------------------------------------------------------

_FOOTNOTE_LEGAL_CONTEXT: re.Pattern[str] = re.compile(
    r"(?i)(ley|artículo|articulo|decreto|numeral|inciso|parágrafo"
    r"|paragrafo|literal|ordinal|resolución|resolucion)\s*$"
)

# ------------------------------------------------------------------
# Semantic image-context words
# ------------------------------------------------------------------

_IMAGE_CONTEXT_RE: re.Pattern[str] = re.compile(
    r"(?i)\b(figura|tabla|imagen|gráfico|grafico|ilustración"
    r"|ilustracion|foto|fotografía|fotografia|esquema|diagrama"
    r"|mapa|mapas|plano|planos|croquis|anexo|anexos|cronograma"
    r"|fase|fases)\b"
)


# ======================================================================
# DATACLASSES FOR DOCUMENT PROFILING, SEGMENTATION, AND QUALITY
# ======================================================================


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

    section_type: (
        str  # metadata, facts, claims, legal_basis, evidence, analysis, decision, citations
    )
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


# ======================================================================
# 1. DOCUMENT PROFILING STAGE
# ======================================================================

# Legal citation patterns for density calculation
_LEGAL_CITATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(ley|decreto|artículo|articulo|sentencia|expediente)\s*\d"),
    re.compile(r"(?i)\b(c\.p\.|c\.c\.|c\.p\.c\.|c\.g\.p\.)\b"),
    re.compile(r"(?i)\bcorte\s+(constitucional|suprema)\b"),
    re.compile(r"(?i)\bconsejo\s+de\s+estado\b"),
    re.compile(r"(?i)\b[TSC]-\d{3,}\b"),  # T-123, C-456, SU-789
    re.compile(r"(?i)\bresolución\s*n?[°º]?\s*\d"),
]

# Coastal/beach law semantic terms
_COASTAL_TERMS: list[str] = [
    "playa",
    "playas",
    "bahía",
    "bahia",
    "bajamar",
    "litoral",
    "erosión",
    "erosion",
    "ocupación",
    "ocupacion",
    "espacio público",
    "espacio publico",
    "dimar",
    "concesión marítima",
    "concesion maritima",
    "bienes de uso público",
    "bienes de uso publico",
    "recuperación costera",
    "recuperacion costera",
    "servidumbre",
    "protección litoral",
    "proteccion litoral",
    "zona costera",
    "franja de playa",
    "línea de costa",
    "linea de costa",
    "pleamar",
    "marea",
    "puerto",
    "muelle",
    "embarcadero",
    "zona de bajamar",
    "terrenos de bajamar",
    "bien público",
    "bien publico",
    "dominio público",
    "dominio publico",
    "restinga",
    "manglar",
    "estuario",
    "acantilado",
    "vertimiento",
    "vertimientos",
    "aguas residuales",
    "emisario submarino",
    "emisario",
    "arrecife",
    "arrecifes",
    "coral",
    "corales",
    "colector pluvial",
    "colector",
    "contaminación marina",
    "contaminacion marina",
    "pradera marina",
    "praderas marinas",
    "pastos marinos",
    "capitanía de puerto",
    "corpamag",
]

_COASTAL_PATTERN: re.Pattern[str] = re.compile(
    r"(?i)\b(" + "|".join(re.escape(term) for term in _COASTAL_TERMS) + r")\b"
)

# OCR noise indicators
_OCR_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[^\w\s]{3,}"),  # Three or more consecutive special chars
    re.compile(r"\d[a-z]\d"),  # Digit-letter-digit (OCR confusion)
    re.compile(r"[a-z]\d[a-z]"),  # Letter-digit-letter
    re.compile(r"[\x00-\x1f]"),  # Control characters
    re.compile(r"[ﬁﬂ]"),  # Ligature artifacts
]

# Footnote indicators
_FOOTNOTE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*\d{1,2}\s+[A-Z]"),  # "1 Some text..."
    re.compile(r"^\s*\[\d+\]"),  # "[1]"
    re.compile(r"^\s*\(\d+\)"),  # "(1)"
    re.compile(r"(?i)^\s*\d{1,2}\s+(ver|véase|cf\.|vid\.)\b"),
]


def _count_pattern_matches(text: str, patterns: list[re.Pattern[str]]) -> int:
    """Count total matches of multiple patterns in text."""
    return sum(len(p.findall(text)) for p in patterns)


def _detect_multi_column(lines: list[str]) -> bool:
    """Heuristic detection of multi-column layout based on line length variance."""
    if len(lines) < 10:
        return False

    lengths = [len(line.strip()) for line in lines if line.strip()]
    if len(lengths) < 10:
        return False

    avg_len = sum(lengths) / len(lengths)
    short_lines = sum(1 for l in lengths if l < avg_len * 0.4)

    # High ratio of short lines may indicate multi-column
    return short_lines / len(lengths) > 0.35


def _detect_heading_consistency(text: str) -> float:
    """Measure consistency of markdown heading usage (0-1)."""
    lines = text.splitlines()
    headings = [l for l in lines if l.strip().startswith("#")]

    if len(headings) < 2:
        return 0.5  # Neutral if insufficient data

    # Check if headings follow a consistent hierarchy
    levels = [len(h.split()[0]) if h.split() else 0 for h in headings]

    # Good consistency: levels don't jump more than 1 at a time
    jumps = sum(1 for i in range(1, len(levels)) if abs(levels[i] - levels[i - 1]) > 1)

    return max(0.0, 1.0 - (jumps / len(headings)))


def profile_legal_document(md_text: str) -> LegalDocumentProfile:
    """
    Analyze a legal document to build a profile for adaptive processing.

    Detects:
    - Text density and structure
    - Repeated header/footer likelihood
    - Legal citation density
    - OCR corruption score
    - Multi-column structure
    - Heading consistency
    - Footnote density
    - Coastal/beach-law semantic density
    """
    lines = md_text.splitlines()
    total_chars = len(md_text)
    total_words = len(md_text.split())

    if total_chars == 0:
        return LegalDocumentProfile()

    # Count legal citation matches
    legal_matches = _count_pattern_matches(md_text, _LEGAL_CITATION_PATTERNS)
    legal_density = legal_matches / max(1, total_words / 100)  # Per 100 words

    # Count OCR noise indicators
    noise_matches = _count_pattern_matches(md_text, _OCR_NOISE_PATTERNS)
    ocr_noise_score = noise_matches / max(1, total_chars / 1000)  # Per 1000 chars

    # Count footnote indicators
    footnote_matches = _count_pattern_matches(md_text, _FOOTNOTE_PATTERNS)
    footnote_density = footnote_matches / max(1, len(lines) / 10)  # Per 10 lines

    # Coastal semantic density
    coastal_matches = len(_COASTAL_PATTERN.findall(md_text))
    coastal_density = coastal_matches / max(1, total_words / 100)  # Per 100 words

    # Detect multi-column layout
    multi_column = _detect_multi_column(lines)

    # Detect heading consistency
    heading_consistency = _detect_heading_consistency(md_text)

    # Estimate page count from common page markers
    page_markers = len(re.findall(r"(?i)(pág\.?\s*\d+|página\s*\d+|\bpage\s*\d+)", md_text))
    total_pages = max(1, page_markers)

    # Check for scanned document indicators (high OCR noise + low text density)
    is_scanned = ocr_noise_score > OCR_NOISE_THRESHOLD * 2

    # Estimate repeated header/footer presence
    repeated_headers = _estimate_repeated_furniture(lines, position="start")
    repeated_footers = _estimate_repeated_furniture(lines, position="end")

    # Count paragraphs
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


def _estimate_repeated_furniture(lines: list[str], position: str = "start") -> bool:
    """Quick estimate if repeated headers/footers are likely present."""
    if len(lines) < 20:
        return False

    # Sample lines from appropriate positions
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

    # Check for repeated short lines (typical headers/footers)
    short_samples = [s for s in samples if 5 < len(s) < 100]
    if not short_samples:
        return False

    counts = Counter(short_samples)
    most_common_count = counts.most_common(1)[0][1] if counts else 0

    return most_common_count >= 3


# ======================================================================
# 2. CAPABILITY-BASED ADAPTIVE CLEANING
# ======================================================================


def adaptive_cleanup(
    md_text: str,
    profile: LegalDocumentProfile,
    md_path: Path | None = None,
) -> str:
    """Apply the full cleanup pipeline to legal document markdown.

    Pipeline order (all steps always execute for legal documents):

    1. ``_strip_frontmatter_noise``    — remove OCR junk before first heading
    2. ``_fix_ocr_chars``              — correct OCR character artifacts
    3. ``_remove_noisy_lines``         — drop high-noise lines
    4. ``repair_layout_breaks``        — merge broken lines from multi-column
    5. ``_remove_internal_references_scored`` — footnote bodies & page refs
    6. ``_remove_figure_legend_clusters``     — map/figure label clusters
    7. ``_reconstruct_paragraphs``     — rejoin split paragraphs
    8. ``_remove_footnote_numbers``    — strip footnote markers from words
    9. ``_remove_repeated_blocks``     — deduplicate headers/footers
    10. ``_filter_images``             — filter irrelevant images
    11. ``_clean_markdown``            — final structural normalization
    """
    md_text = _strip_frontmatter_noise(md_text)
    md_text = _fix_ocr_chars(md_text)
    md_text = _remove_noisy_lines(md_text)
    md_text = repair_layout_breaks(md_text)
    md_text = _remove_internal_references_scored(md_text)
    md_text = _remove_footnote_citation_blocks(md_text)
    md_text = _remove_figure_legend_clusters(md_text)
    md_text = _reconstruct_paragraphs(md_text)
    md_text = _remove_footnote_numbers(md_text)
    md_text = _remove_repeated_blocks(md_text)

    if md_path is not None:
        md_text = _filter_images(md_text, md_path)

    md_text = _clean_markdown(md_text)

    return md_text


# ======================================================================
# 3. HEADER/FOOTER DETECTION BY PAGE FREQUENCY
# ======================================================================


def detect_repeated_page_furniture(pages: list[str]) -> set[str]:
    """
    Detect repeated header/footer lines using page frequency analysis.

    Analyzes the first and last 2 lines of each page, calculates normalized
    frequency, and marks lines appearing in >= 60% of pages.
    """
    if len(pages) < 3:
        return set()

    # Collect candidate lines from page boundaries
    line_counts: Counter[str] = Counter()

    for page in pages:
        page_lines = [l.strip() for l in page.splitlines() if l.strip()]
        if len(page_lines) < 4:
            continue

        # First 2 lines (potential headers)
        for line in page_lines[:2]:
            normalized = _normalize_furniture_line(line)
            if normalized and 3 < len(normalized) < 150:
                line_counts[normalized] += 1

        # Last 2 lines (potential footers)
        for line in page_lines[-2:]:
            normalized = _normalize_furniture_line(line)
            if normalized and 3 < len(normalized) < 150:
                line_counts[normalized] += 1

    # Calculate threshold
    threshold = len(pages) * REPEATED_FURNITURE_THRESHOLD

    # Find repeated lines
    repeated = {line for line, count in line_counts.items() if count >= threshold}

    logger.debug(f"Detected {len(repeated)} repeated furniture lines across {len(pages)} pages")

    return repeated


def _normalize_furniture_line(line: str) -> str:
    """Normalize a line for furniture comparison (fuzzy matching)."""
    # Remove page numbers and common variations
    normalized = re.sub(r"\b(pág\.?|página|page)\s*\d+\b", "", line, flags=re.IGNORECASE)
    normalized = re.sub(r"\b\d{1,4}\s*$", "", normalized)  # Trailing page number
    normalized = re.sub(r"^\s*\d{1,4}\s+", "", normalized)  # Leading page number
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return normalized


def remove_page_furniture(md_text: str, repeated_lines: set[str]) -> str:
    """Remove identified repeated header/footer lines from text."""
    if not repeated_lines:
        return md_text

    lines = md_text.splitlines()
    cleaned = []

    for line in lines:
        normalized = _normalize_furniture_line(line)
        if normalized not in repeated_lines:
            cleaned.append(line)

    return "\n".join(cleaned)


def _split_into_pages(md_text: str) -> list[str]:
    """
    Split markdown text into approximate pages.
    Uses page markers or fixed-length heuristics.
    """
    # Try to split on page markers
    page_pattern = re.compile(r"\n(?=(?:pág\.?\s*\d+|página\s*\d+|---+\s*\d+))", re.IGNORECASE)

    pages = page_pattern.split(md_text)

    if len(pages) < 3:
        # Fall back to paragraph-based splitting (approximate page length)
        paragraphs = md_text.split("\n\n")
        pages = []
        current_page: list[str] = []
        current_len = 0

        for para in paragraphs:
            current_page.append(para)
            current_len += len(para)

            if current_len > 3000:  # Approximate page length
                pages.append("\n\n".join(current_page))
                current_page = []
                current_len = 0

        if current_page:
            pages.append("\n\n".join(current_page))

    return pages


# ======================================================================
# 4. HEURISTIC SCORING FOR INTERNAL REFERENCES
# ======================================================================


def is_legal_internal_reference(line: str) -> bool:
    """
    Classify a line as an internal reference using heuristic scoring.

    Scoring signals (weighted):
    - "ver pág", "folio", "cuaderno" references
    - PDF references
    - Expediente references
    - OneDrive/HTTP links
    - Isolated legal citation starters
    - Short footnote body indicators
    """
    score = _score_internal_reference(line)
    return score >= INTERNAL_REF_SCORE_THRESHOLD


def _score_internal_reference(line: str) -> int:
    """Calculate internal reference score for a line.

    Lines scoring >= ``INTERNAL_REF_SCORE_THRESHOLD`` (3) are removed.
    """
    score = 0
    stripped = line.strip()
    line_lower = stripped.lower()

    # === High confidence signals (+3) ===
    if re.search(r"(?i)^\s*\d{0,2}\s*ver\s+p[aá]gs?\.?\s*\d", line):
        score += 3
    if re.search(r"(?i)^\s*\d{0,2}\s*ver\s+pdf\b", line):
        score += 3
    if re.search(r"(?i)\bver\s+pdf\s*:?\s*\d+\b", line):
        score += 3
    if re.search(r"(?i)\bver\s+folio\b", line):
        score += 3

    # Numbered footnote body lines: "N  <text>" where N is 1-2 digits and
    # the text starts with a capital letter or a known footnote starter.
    # This is the dominant footnote format in Colombian tribunal documents.
    if re.match(r"^\s*\d{1,2}\s{2,}[A-ZÁÉÍÓÚÜÑ]", stripped):
        score += 3
    if re.match(r"^\s*\d{1,2}\s{2,}[a-záéíóúüñ]", stripped):
        # Lowercase start after wide gap — also a footnote body
        score += 3

    # === Medium confidence signals (+2) ===
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
    # "En adelante X" — abbreviation footnote
    if re.search(r"(?i)^\s*\d{1,2}\s+en adelante\b", line):
        score += 3
    # "Al respecto ver..." — cross-reference footnote
    if re.search(r"(?i)^\s*\d{1,2}\s+al respecto\b", line):
        score += 3
    # "M.P. Nombre" — magistrado ponente footnote
    if re.search(r"(?i)^\s*\d{1,2}\s+m\.p\.\b", line):
        score += 3
    # Corte Constitucional / Consejo de Estado / Sección footnotes
    if re.search(
        r"(?i)^\s*\d{1,2}\s+(corte constitucional|consejo de estado"
        r"|sección primera|sala plena|sala de lo contencioso)\b",
        line,
    ):
        score += 3
    # "En cumplimiento de la Ley..." — long meta-footnote
    if re.search(r"(?i)^\s*\d{1,2}\s+en cumplimiento\b", line):
        score += 3
    # "Vale la pena anotar que..." footnote
    if re.search(r"(?i)^\s*\d{1,2}\s+vale la pena\b", line):
        score += 3
    # "Presentación de la demanda..." procedural timeline footnote
    if re.search(r"(?i)^\s*\d{1,2}\s+presentación de la demanda\b", line):
        score += 3
    # "T-519 de 1992" / "SU-540 de 2007" — jurisprudence reference
    if re.search(r"(?i)^\s*\d{1,2}\s+[A-Za-z]{1,3}-\d{3,}\b", line):
        score += 3
    # "Por el cual se..." — decree/resolution description footnote
    if re.search(r"(?i)^\s*\d{1,2}\s+por (el|la|lo) cual\b", line):
        score += 3

    # === Bare footnote number (just digits, possibly with trailing quote) ===
    if re.match(r"^\s*\d{1,2}\s*['\u2018\u2019\u201C\u201D]?\s*$", stripped):
        score += 3

    # Footnote-embedded citation metadata (from fragmented multi-column OCR)
    if re.match(
        r"(?i)^\s*\d{0,2}\s*(radicaci[oó]n|demandante|demandados?|ponente"
        r"|magistrad[oa]|secretari[oa])\s*:",
        stripped,
    ):
        if len(stripped) < 120:
            score += 3

    # Decree/resolution title footnotes: "Por medio del cual se expide..."
    if re.match(r"(?i)^por\s+medio\s+del\s+cual\s+se\b", stripped):
        if len(stripped) < 120:
            score += 3

    # === Lower confidence signals (+1) ===
    if re.search(r"(?i)^\s*p[aá]g\.?\s*\d+\s*$", line):
        score += 1
    if re.search(r"(?i)^\s*ver\s+considerando\b", line):
        score += 1
    # PDF page references within a line (not just at start)
    if re.search(r"(?i)\bpdf\s+\d{2}\s+del\s+expediente\b", line):
        score += 2
    if re.search(r"(?i)\bexpediente\s+electrónico\s+judicial\b", line):
        score += 2

    # === Boost for short lines that already have a signal ===
    if len(line_lower) < 80 and score > 0:
        score += 1

    return score


def _remove_internal_references_scored(text: str) -> str:
    """Remove internal references using heuristic scoring."""
    # Strip inline "pág. N" prefixes
    text = re.sub(
        r"(?im)^\s*p[aá]g\.?\s*\d+\s+(?=[a-záéíóúüñ])",
        "",
        text,
    )

    lines = text.splitlines()
    cleaned = [line for line in lines if not is_legal_internal_reference(line)]
    return "\n".join(cleaned)


# ------------------------------------------------------------------
# 4b. FOOTNOTE CITATION BLOCK REMOVAL
# ------------------------------------------------------------------

_CITATION_ANCHOR_RE = re.compile(
    r"(?i)Radicaci[oó]n:\s*\d{2,}|"
    r"Referencia:\s*medio\s+de\s+control|"
    r"[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+\s+[A-ZÁÉÍÓÚÜÑ]"
    r"[a-záéíóúüñ]+\.\s+Bogot[aá]"
)

_CITATION_FRAGMENT_RE = re.compile(
    r"(?i)^("
    r"\d{5}-\d+\.\s*Demandante:|"  # "00987-01.  Demandante:"
    r"General\s+de\b|"  # "General de"
    r"Delegad[oa]\s+para\b|"  # "Delegada para"
    r"la\s+Naci[oó]n$|"  # "la Nación"
    r"Procuradur[ií]a$|"  # "Procuraduría"
    r"Nacional\s+de\s+Licencias\b|"  # "Nacional de Licencias"
    r"-$|"  # bare dash
    r"Ambientales\s+y\s+Agrarios|"
    r"Asuntos$|"
    r"Naci[oó]n\s*-\s*Ministerio\b|"  # "Nación - Ministerio..."
    r".*-\s*ANLA\b|"  # "...ANLA - otros"
    r".*-\s*otros\.\s*$"  # "...Autoridad - otros."
    r")"
)


def _remove_footnote_citation_blocks(text: str) -> str:
    """Remove multi-paragraph footnote citation blocks from cited decisions.

    These blocks contain the cited decision's metadata (Radicación, parties,
    judge name) spread across many short fragmented lines produced by
    multi-column OCR.  They are identified by an anchor line containing a
    recognizable citation pattern, followed by short fragment lines.
    """
    paragraphs = text.split("\n\n")
    to_remove: set[int] = set()

    for idx, para in enumerate(paragraphs):
        stripped = para.strip()
        if not stripped:
            continue

        if not _CITATION_ANCHOR_RE.search(stripped):
            continue

        if stripped.startswith("#") or stripped.startswith("|"):
            continue

        # Found an anchor.  Mark it and scan forward for fragment lines.
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


# ======================================================================
# 5. LAYOUT-AWARE RECONSTRUCTION
# ======================================================================


def repair_layout_breaks(md_text: str) -> str:
    """
    Repair layout breaks from multi-column PDFs and page boundaries.

    - Detects broken paragraphs at page boundaries
    - Repairs column bleed
    - Merges soft line breaks
    - Preserves: real headings, legal enumerations, bullet claims, judicial decision blocks
    """
    lines = md_text.splitlines()
    result: list[str] = []
    i = 0

    while i < len(lines):
        current = lines[i]
        stripped = current.strip()

        # Preserve empty lines
        if not stripped:
            result.append(current)
            i += 1
            continue

        # Preserve headings
        if stripped.startswith("#"):
            result.append(current)
            i += 1
            continue

        # Preserve legal enumerations (1., 2., a), b), etc.)
        if _is_legal_enumeration(stripped):
            result.append(current)
            i += 1
            continue

        # Preserve bullet points
        if stripped.startswith(("-", "*", "•")):
            result.append(current)
            i += 1
            continue

        # Preserve judicial decision blocks (RESUELVE, FALLA, etc.)
        if _is_decision_block_start(stripped):
            result.append(current)
            i += 1
            continue

        # Check if this line should be merged with the next
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()

            if _should_merge_lines(stripped, next_line):
                # Merge with next line
                merged = stripped.rstrip() + " " + next_line.lstrip()
                result.append(merged)
                i += 2
                continue

        result.append(current)
        i += 1

    return "\n".join(result)


def _is_legal_enumeration(line: str) -> bool:
    """Check if line starts a legal enumeration."""
    patterns = [
        r"^\d{1,3}\.\s",  # "1. ", "12. "
        r"^[a-z]\)\s",  # "a) "
        r"^[ivxIVX]+\.\s",  # "i. ", "iv. "
        r"^[A-Z]\.\s",  # "A. "
        r"^\([a-z]\)\s",  # "(a) "
        r"^\(\d+\)\s",  # "(1) "
        r"^(?:PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO)[\.:]\s*",  # Spanish ordinals
    ]
    return any(re.match(p, line) for p in patterns)


def _is_decision_block_start(line: str) -> bool:
    """Check if line starts a judicial decision block."""
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
    """Determine if two lines should be merged (broken paragraph)."""
    if not current or not next_line:
        return False

    # Don't merge if next line is special
    if next_line.startswith(("#", "-", "*", "•")):
        return False
    if _is_legal_enumeration(next_line):
        return False
    if _is_decision_block_start(next_line):
        return False

    # Don't merge if current ends with sentence terminator
    if current.rstrip()[-1:] in ".;:!?":
        return False

    # Merge if: current doesn't end with terminator AND next starts with lowercase
    last_char = current.rstrip()[-1:] if current.rstrip() else ""
    first_char = next_line[0] if next_line else ""

    ends_mid_sentence = last_char not in ".;:!?\"')"
    next_continues = first_char.islower()

    return ends_mid_sentence and next_continues


# ======================================================================
# 6. SEMANTIC LEGAL SECTION SEGMENTATION
# ======================================================================

# Section classification patterns
_SECTION_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "metadata": [
        re.compile(
            r"(?i)^(república|republica|tribunal|juzgado|sala|radicación|radicacion|expediente)"
        ),
        re.compile(r"(?i)^(magistrado|magistrada|ponente|secretario|secretaria)"),
        re.compile(r"(?i)^(demandante|demandado|actor|accionante|accionado)"),
    ],
    "facts": [
        re.compile(r"(?i)\b(hechos|antecedentes|síntesis|sintesis|resumen)\b"),
        re.compile(r"(?i)\b(situación fáctica|situacion factica|contexto)\b"),
    ],
    "claims": [
        re.compile(r"(?i)\b(pretensión|pretension|pretensiones|solicita|solicitud)\b"),
        re.compile(r"(?i)\b(pide|petición|peticion|demanda)\b"),
    ],
    "legal_basis": [
        re.compile(r"(?i)\b(ley|decreto|artículo|articulo|constitución|constitucion)\b"),
        re.compile(r"(?i)\b(norma|código|codigo|reglamento|resolución|resolucion)\b"),
        re.compile(r"(?i)\b(fundamento|fundamentos|marco jurídico|marco juridico)\b"),
    ],
    "evidence": [
        re.compile(r"(?i)\b(prueba|pruebas|peritaje|dictamen|testimonio)\b"),
        re.compile(r"(?i)\b(documento|documentos|acervo probatorio)\b"),
        re.compile(r"(?i)\b(inspección|inspeccion|reconocimiento)\b"),
    ],
    "analysis": [
        re.compile(r"(?i)\b(considera|considerando|consideraciones|análisis|analisis)\b"),
        re.compile(r"(?i)\b(problema jurídico|problema juridico|estudio|valoración|valoracion)\b"),
    ],
    "decision": [
        re.compile(r"(?i)\b(resuelve|falla|decide|niega|concede|ordena)\b"),
        re.compile(r"(?i)\b(declara|condena|absuelve|accede|deniega)\b"),
    ],
    "citations": [
        re.compile(r"(?i)\b(sentencia\s+[TC]-\d+|corte\s+constitucional)\b"),
        re.compile(r"(?i)\b(consejo\s+de\s+estado|jurisprudencia)\b"),
    ],
}


def segment_legal_sections(md_text: str) -> list[LegalBlock]:
    """
    Segment legal document into semantic sections.

    Section types:
    - metadata: document identification, parties, court info
    - facts: background, antecedents, factual context
    - claims: petitions, requests, demands
    - legal_basis: laws, articles, constitutional basis
    - evidence: proofs, expert reports, testimonies
    - analysis: legal reasoning, considerations
    - decision: rulings, orders, resolutions
    - citations: referenced jurisprudence
    """
    paragraphs = [p.strip() for p in md_text.split("\n\n") if p.strip()]
    blocks: list[LegalBlock] = []

    for para in paragraphs:
        section_type, score = _classify_paragraph(para)
        coastal_relevance = _calculate_coastal_relevance(para)

        blocks.append(
            LegalBlock(
                section_type=section_type,
                text=para,
                score=score,
                coastal_relevance=coastal_relevance,
            )
        )

    return blocks


def _classify_paragraph(paragraph: str) -> tuple[str, float]:
    """Classify a paragraph into a legal section type with confidence score."""
    scores: dict[str, float] = {section: 0.0 for section in _SECTION_PATTERNS}

    para_lower = paragraph.lower()

    for section, patterns in _SECTION_PATTERNS.items():
        for pattern in patterns:
            matches = len(pattern.findall(para_lower))
            scores[section] += matches

    # Position-based boost (metadata usually at start)
    if paragraph.startswith(
        ("República", "REPÚBLICA", "Tribunal", "TRIBUNAL", "Juzgado", "JUZGADO")
    ):
        scores["metadata"] += 2

    # Find best match
    best_section = max(scores, key=scores.get)  # type: ignore
    best_score = scores[best_section]

    # Default to 'analysis' if no clear match
    if best_score < 1:
        return "analysis", 0.0

    # Normalize score to 0-1 range
    normalized_score = min(1.0, best_score / 5.0)

    return best_section, normalized_score


def _calculate_coastal_relevance(paragraph: str) -> float:
    """Calculate coastal/beach law relevance score for a paragraph."""
    matches = len(_COASTAL_PATTERN.findall(paragraph))
    words = len(paragraph.split())

    if words == 0:
        return 0.0

    # Coastal matches per 100 words, capped at 1.0
    relevance = min(1.0, (matches * 100) / words)

    return relevance


# ======================================================================
# 7. COASTAL LEGAL ENTITY EXTRACTION
# ======================================================================

# Entity patterns for coastal legal terms
_COASTAL_ENTITY_PATTERNS: dict[str, re.Pattern[str]] = {
    "playa": re.compile(r"(?i)\b(playa|playas)\b"),
    "bahia": re.compile(r"(?i)\b(bahía|bahia|bahías|bahias)\b"),
    "bajamar": re.compile(r"(?i)\b(bajamar|zona de bajamar|terrenos de bajamar)\b"),
    "litoral": re.compile(r"(?i)\b(litoral|línea de costa|linea de costa|zona costera)\b"),
    "erosion": re.compile(r"(?i)\b(erosión|erosion|erosión costera|erosion costera)\b"),
    "ocupacion": re.compile(r"(?i)\b(ocupación|ocupacion|ocupación indebida|ocupacion indebida)\b"),
    "espacio_publico": re.compile(
        r"(?i)\b(espacio público|espacio publico|bien público|bien publico)\b"
    ),
    "dimar": re.compile(r"(?i)\b(dimar|dirección general marítima|direccion general maritima)\b"),
    "concesion_maritima": re.compile(
        r"(?i)\b(concesión marítima|concesion maritima|permiso marítimo|permiso maritimo)\b"
    ),
    "bienes_uso_publico": re.compile(
        r"(?i)\b(bienes de uso público|bienes de uso publico|dominio público|dominio publico)\b"
    ),
    "recuperacion_costera": re.compile(
        r"(?i)\b(recuperación costera|recuperacion costera|restauración costera|restauracion costera)\b"
    ),
    "servidumbre": re.compile(
        r"(?i)\b(servidumbre|servidumbre de tránsito|servidumbre de transito)\b"
    ),
    "proteccion_litoral": re.compile(
        r"(?i)\b(protección litoral|proteccion litoral|protección costera|proteccion costera)\b"
    ),
    "pleamar": re.compile(r"(?i)\b(pleamar|marea alta|nivel de pleamar)\b"),
    "manglar": re.compile(r"(?i)\b(manglar|manglares|zona de manglar)\b"),
    "puerto": re.compile(
        r"(?i)\b(puerto|muelle|embarcadero|terminal portuario|terminal portuaria)\b"
    ),
    "estuario": re.compile(r"(?i)\b(estuario|estuarios|desembocadura)\b"),
    "restinga": re.compile(r"(?i)\b(restinga|restingas)\b"),
    "acantilado": re.compile(r"(?i)\b(acantilado|acantilados|risco|riscos)\b"),
    "vertimiento": re.compile(
        r"(?i)\b(vertimiento|vertimientos|aguas residuales|aguas servidas)\b"
    ),
    "emisario": re.compile(r"(?i)\b(emisario submarino|emisario|emisarios)\b"),
    "arrecife": re.compile(
        r"(?i)\b(arrecife|arrecifes|formación arrecifal|formacion arrecifal|coral|corales)\b"
    ),
    "colector_pluvial": re.compile(
        r"(?i)\b(colector pluvial|colector|colectores|sistema de drenaje pluvial)\b"
    ),
    "contaminacion_marina": re.compile(
        r"(?i)\b(contaminación marina|contaminacion marina"
        r"|contaminación del mar|contaminacion del mar|contaminación costera)\b"
    ),
    "pradera_marina": re.compile(
        r"(?i)\b(pradera marina|praderas marinas|pastos marinos|algas marinas)\b"
    ),
    "capitania": re.compile(r"(?i)\b(capitanía de puerto|capitania de puerto|capitanía)\b"),
    "corpamag": re.compile(
        r"(?i)\b(corpamag|corporación autónoma regional del magdalena"
        r"|corporacion autonoma regional del magdalena)\b"
    ),
}


def extract_coastal_legal_entities(md_text: str) -> dict[str, list[str]]:
    """
    Extract and normalize coastal legal entities from document text.

    Returns a dictionary mapping entity types to unique normalized values found.
    """
    entities: dict[str, set[str]] = {key: set() for key in _COASTAL_ENTITY_PATTERNS}

    for entity_type, pattern in _COASTAL_ENTITY_PATTERNS.items():
        matches = pattern.findall(md_text)
        for match in matches:
            # Handle tuple matches (from groups in patterns)
            if isinstance(match, tuple):
                match = match[0]
            normalized = _normalize_entity(match)
            entities[entity_type].add(normalized)

    # Convert sets to sorted lists and remove empty entries
    return {entity_type: sorted(values) for entity_type, values in entities.items() if values}


def _normalize_entity(entity: str) -> str:
    """Normalize an entity string for consistent representation."""
    # Lowercase and strip whitespace
    normalized = entity.lower().strip()
    # Normalize accented characters for consistency
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


# ======================================================================
# 8. AUTOMATED QUALITY EVALUATION
# ======================================================================


def evaluate_document_quality(
    original_md: str,
    cleaned_md: str,
    blocks: list[LegalBlock],
    entities: dict[str, list[str]],
    profile: LegalDocumentProfile,
) -> DocumentQualityReport:
    """
    Evaluate document processing quality.

    Scoring weights:
    - Paragraph reconstruction: 20%
    - Header/footer cleanup: 15%
    - OCR correction: 15%
    - Legal reference cleanup: 10%
    - Section segmentation: 20%
    - Coastal entity extraction: 20%
    """
    # Calculate individual scores (0-100)

    # Paragraph score: compare structure before/after
    paragraph_score = _score_paragraph_reconstruction(original_md, cleaned_md)

    # Heading score: measure heading consistency
    heading_score = profile.heading_consistency * 100

    # OCR cleanup score: high noise → low score, capped so it never hits 0
    # for documents with moderate noise.
    if profile.ocr_noise_score <= OCR_NOISE_THRESHOLD:
        ocr_score = 100.0
    else:
        ocr_score = max(20.0, 100.0 - ((profile.ocr_noise_score - OCR_NOISE_THRESHOLD) * 200))

    # Footer removal: all documents get cleaned now, so score based on
    # whether the cleaned text still contains suspected furniture.
    footer_score = _score_footer_removal(cleaned_md)

    # Citation cleanup score: based on remaining internal references
    citation_score = _score_citation_cleanup(cleaned_md)

    # Section segmentation score: diversity and coverage
    segmentation_score = _score_segmentation(blocks)

    # Coastal entity score: based on extraction richness
    entity_score = _score_entity_extraction(entities, profile)

    # Calculate weighted final score
    final_quality = (
        paragraph_score * 0.20
        + footer_score * 0.15
        + ocr_score * 0.15
        + citation_score * 0.10
        + segmentation_score * 0.20
        + entity_score * 0.20
    )

    # Count sections
    section_counts = Counter(block.section_type for block in blocks)

    # Count total entities
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


def _score_paragraph_reconstruction(original: str, cleaned: str) -> float:
    """Score paragraph reconstruction quality.

    Checks both consolidation ratio AND the presence of broken paragraphs
    (lines ending without terminator followed by lowercase continuation).
    """
    orig_paras = len([p for p in original.split("\n\n") if p.strip()])
    clean_paras = [p for p in cleaned.split("\n\n") if p.strip()]

    if orig_paras == 0:
        return 50.0

    # Consolidation component (0-50 points)
    ratio = len(clean_paras) / orig_paras
    if 0.4 <= ratio <= 0.85:
        consolidation = 50.0
    elif 0.85 < ratio <= 1.0:
        consolidation = 35.0
    else:
        consolidation = 20.0

    # Broken-paragraph component (0-50 points): penalize remaining breaks
    broken = 0
    for i in range(len(clean_paras) - 1):
        cur = clean_paras[i].strip()
        nxt = clean_paras[i + 1].strip()
        if (
            cur
            and nxt
            and cur[-1] not in ".;:?!\"')"
            and nxt[0].islower()
            and not nxt.startswith(("#", "-", "*"))
        ):
            broken += 1

    break_ratio = broken / max(1, len(clean_paras))
    integrity = max(0.0, 50.0 - break_ratio * 200)

    return min(100.0, consolidation + integrity)


def _score_footer_removal(cleaned_md: str) -> float:
    """Score footer/header removal effectiveness on the cleaned text."""
    lines = [l.strip() for l in cleaned_md.splitlines() if l.strip()]
    if not lines:
        return 50.0

    # Count lines that look like remaining footnote bodies
    footnote_body_re = re.compile(r"^\d{1,2}\s{2,}")
    remaining = sum(1 for l in lines if footnote_body_re.match(l))
    ratio = remaining / len(lines)
    return max(0.0, min(100.0, 100 - ratio * 1000))


def _score_citation_cleanup(cleaned_md: str) -> float:
    """Score internal reference cleanup effectiveness.

    Counts remaining lines that match footnote body or page-reference
    patterns and penalizes proportionally.
    """
    lines = cleaned_md.splitlines()
    if not lines:
        return 50.0

    # Use both the scored classifier AND simpler heuristic patterns
    remaining_refs = sum(1 for line in lines if is_legal_internal_reference(line))

    # Also count "N  En adelante" / "N  Ver" / "N  Corte" patterns that
    # might score below threshold individually
    simple_fn = re.compile(r"^\s*\d{1,2}\s{2,}(En|Ver|Al|Corte|Consejo|Por|M\.P)", re.IGNORECASE)
    remaining_refs += sum(1 for line in lines if simple_fn.match(line.strip()))

    ref_ratio = remaining_refs / len(lines)
    return max(0.0, min(100.0, 100 - ref_ratio * 800))


def _score_segmentation(blocks: list[LegalBlock]) -> float:
    """Score section segmentation quality."""
    if not blocks:
        return 0.0

    # Count unique section types found
    types_found = set(block.section_type for block in blocks)

    # Ideal: finding multiple different section types
    type_diversity = len(types_found) / 8  # 8 possible types

    # Average confidence scores
    avg_confidence = sum(block.score for block in blocks) / len(blocks)

    # Coastal relevance bonus
    coastal_blocks = sum(1 for b in blocks if b.coastal_relevance > 0.1)
    coastal_bonus = min(0.2, coastal_blocks / len(blocks))

    score = (type_diversity * 50) + (avg_confidence * 30) + (coastal_bonus * 100)

    return min(100.0, score)


def _score_entity_extraction(
    entities: dict[str, list[str]],
    profile: LegalDocumentProfile,
) -> float:
    """Score coastal entity extraction quality."""
    # Number of entity types found
    types_found = len(entities)

    # Total entities extracted
    total_entities = sum(len(values) for values in entities.values())

    # Expected based on coastal density in profile
    expected_types = max(1, profile.coastal_semantic_density * 50)

    coverage = min(1.0, types_found / expected_types)
    richness = min(1.0, total_entities / 10)  # 10 entities is good

    # Bonus for finding key coastal terms
    key_terms = {"dimar", "playa", "bajamar", "ocupacion", "espacio_publico"}
    key_found = sum(1 for k in key_terms if k in entities)
    key_bonus = key_found / len(key_terms)

    score = (coverage * 40) + (richness * 30) + (key_bonus * 30)

    return min(100.0, score * 100)


# ======================================================================
# ORIGINAL UTILITY FUNCTIONS (PRESERVED/UPDATED)
# ======================================================================


def _strip_frontmatter_noise(text: str) -> str:
    """Remove OCR noise lines that precede the first real heading.

    The first pages of Colombian tribunal PDFs often contain institutional
    banners, seals, phone numbers, social-media handles and decorative text
    that Docling extracts verbatim.  Everything before the first ``## ``
    heading that does NOT look like meaningful legal prose is discarded.
    """
    lines = text.splitlines()
    first_heading_idx = None
    for idx, line in enumerate(lines):
        if line.strip().startswith("## "):
            first_heading_idx = idx
            break

    if first_heading_idx is None or first_heading_idx < 2:
        return text

    # Keep only preamble lines that look like real prose (>60 chars, mostly
    # alphabetic, not all-caps noise, and not phone numbers / handles).
    _junk_re = re.compile(
        r"^("
        r"\d{7,}"  # phone numbers
        r"|[A-Z@#·\s\-\.\d]{3,50}$"  # ALL-CAPS noise / handles
        r"|.{0,5}$"  # very short fragments
        r"|.*[@#].*"  # social media handles
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
        # Lines with very low alphabetic density are noise
        alpha = sum(1 for c in stripped if c.isalpha())
        if len(stripped) > 0 and alpha / len(stripped) < 0.5:
            continue
        kept_preamble.append(line)

    return "\n".join(kept_preamble + lines[first_heading_idx:])


def _remove_figure_legend_clusters(text: str) -> str:
    """Remove clusters of short lines that are map/figure legend artifacts.

    When Docling extracts text from embedded maps or diagrams it produces
    runs of 3+ consecutive short lines (< 35 chars each) with no verbs or
    connectors — just place names, units, legend labels.  These pollute
    the legal text with noise.
    """
    _CONNECTOR_RE = re.compile(
        r"(?i)\b(que|para|por|con|sin|como|según|entre|sobre|bajo"
        r"|durante|mediante|desde|hasta|siendo|puede|debe|tiene"
        r"|está|fue|han|será|son|del|los|las|una|uno|este|esta)\b"
    )
    paragraphs = text.split("\n\n")
    result: list[str] = []

    for para in paragraphs:
        lines = [l.strip() for l in para.splitlines() if l.strip()]
        if len(lines) < 3:
            result.append(para)
            continue

        short_count = sum(1 for l in lines if len(l) < 35)
        if short_count < 3 or short_count / len(lines) < 0.6:
            result.append(para)
            continue

        joined = " ".join(lines)
        if _CONNECTOR_RE.search(joined):
            result.append(para)
            continue

        # Cluster of short lines with no linguistic connectors → discard
        continue

    return "\n\n".join(result)


def _fix_ocr_chars(text: str) -> str:
    """Fix common OCR artifacts in Spanish legal documents."""
    img_token_re = re.compile(r"(!\[[^\]]*\]\([^)]+\))")
    parts = img_token_re.split(text)

    result_parts: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            result_parts.append(part)
        else:
            for pattern, replacement in _OCR_CORRECTIONS:
                part = pattern.sub(replacement, part)
            result_parts.append(part)

    return "".join(result_parts)


_INSTITUTIONAL_NOISE_RE = re.compile(
    r"^("
    r"\d{7,}\s*\S{0,30}$"  # phone number + short label
    r"|[A-Za-z]*@\S+$"  # social media handle
    r"|[XxYy][\s@]?\S{0,30}$"  # platform handle "X@...", "YeuTube"
    r"|(?:YouTube|YeuTube|Facebook|Instagram|Twitter)\b.*$"
    r"|[a-z]\d{2}[a-z]\w{0,30}$"  # institutional handle "d01tribunalmag"
    r")",
    re.IGNORECASE,
)


def _remove_noisy_lines(text: str, noise_ratio: float = NOISE_CHAR_RATIO) -> str:
    """Remove lines with high ratio of non-linguistic characters
    and institutional noise (phone numbers, social handles)."""
    cleaned: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue
        if _MD_STRUCTURE_RE.match(stripped):
            cleaned.append(line)
            continue
        if _INSTITUTIONAL_NOISE_RE.match(stripped):
            continue
        non_linguistic = sum(1 for c in stripped if not c.isalnum() and not c.isspace())
        if non_linguistic / len(stripped) < noise_ratio:
            cleaned.append(line)
    return "\n".join(cleaned)


_DANGLING_TAIL_RE = re.compile(
    r"(?i)\b(y|e|o|u|que|de|del|la|el|los|las|en|con|por|para|su|sus"
    r"|una|un|al|como|sin|ni|sobre|bajo|ante|entre|desde|hasta"
    r"|dicha|dicho|dichas|dichos|cuyo|cuya|cuyos|cuyas"
    r"|esta|este|estos|estas|aquel|aquella|todo|toda|cada"
    r"|ser|siendo|ha|han|fue|ser[aá]|deber[aá]|podr[aá])\s*$"
)


def _reconstruct_paragraphs(text: str) -> str:
    """Reconstruct paragraphs broken by page splits.

    Runs two sub-passes:
    1. Rejoin hyphenated word breaks (intra-line).
    2. Merge paragraph pairs split across page boundaries.
       The merge loop runs up to 3 iterations so that chains
       (A broken→B broken→C) are joined progressively.
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

            # Look ahead, skipping empty paragraphs
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


def _should_merge_paragraphs(current: str, next_para: str) -> bool:
    """Decide whether two paragraphs split by a page break should be merged."""
    if not current or not next_para:
        return False
    if current.startswith("#"):
        return False

    # Protect headings, bullet lists, and legal numbered items
    if next_para.startswith("#"):
        return False
    if re.match(r"^- \?", next_para):
        return False
    if re.match(r"^[*\-]\s+[A-ZÁÉÍÓÚÜÑ]", next_para):
        return False
    if len(next_para) > 1 and next_para[0].isdigit() and next_para[1] in ".)":
        return False

    last_char = current[-1]
    first_char = next_para[0]

    # Treat quote-period endings as terminators: "texto.'", "texto.'"
    tail = current[-3:] if len(current) >= 3 else current
    if re.search(r"[.;:?!]['\u2019\u201D\"]\s*$", tail):
        return False

    ends_without_terminator = last_char not in ".;:?!\"')»"
    next_starts_lower = first_char.islower()

    if ends_without_terminator and next_starts_lower:
        return True

    # "- que acredite" where the dash is a page-break OCR artifact
    if re.match(r"^-\s+[a-záéíóúüñ]", next_para) and ends_without_terminator:
        return True

    # Dangling tail: current ends with a conjunction / preposition / article
    if _DANGLING_TAIL_RE.search(current):
        return True

    # Comma at end + lowercase continuation
    if last_char == "," and next_starts_lower:
        return True

    return False


def _remove_footnote_numbers(text: str) -> str:
    """Remove footnote markers from the text.

    Handles three patterns:

    1. **Glued**: ``jurisdicción14`` — word immediately followed by 1-2 digits.
    2. **Spaced**: ``contestó 6`` / ``demanda 14`` — word + whitespace + 1-2
       digits standing alone (Docling often inserts spaces around superscripts).
    3. **Year+digit**: ``20228`` — 4-digit year with a trailing footnote digit.

    Legal context protection prevents stripping digits that follow citation
    keywords (ley, artículo, decreto, etc.) within 40 chars to the left.
    """
    _CITATION_WORD = re.compile(
        r"(?i)^(ley|artículo|articulo|decreto|numeral|inciso|parágrafo"
        r"|paragrafo|literal|ordinal|resolución|resolucion)$"
    )

    # Pass 1: glued — "DIMAR2", "jurisdicción14"
    word_digit_glued = re.compile(
        r"([A-Za-záéíóúüñÁÉÍÓÚÜÑ]{2,})(\d{1,2})\b(?!\d)",
        re.UNICODE,
    )

    def _replace_glued(m: re.Match[str]) -> str:
        word_part = m.group(1)
        preceding = text[max(0, m.start() - 40) : m.start()]
        if _FOOTNOTE_LEGAL_CONTEXT.search(preceding):
            return m.group(0)
        if _CITATION_WORD.match(word_part):
            return m.group(0)
        return word_part

    text = word_digit_glued.sub(_replace_glued, text)

    # Pass 2: spaced — "contestó 6", "demanda  14  manifestando"
    #   word + 1+ spaces + 1-2 digit number + word-boundary (not more digits)
    #   Only match when the digit is NOT preceded by a legal keyword.
    word_space_digit = re.compile(
        r"([A-Za-záéíóúüñÁÉÍÓÚÜÑ]{2,})"  # word of >= 2 letters
        r"(\s+)"  # one or more spaces
        r"(\d{1,2})"  # 1-2 digit footnote marker
        r"(?=\s|[.,;:!?\)\]\"\']|$)"  # followed by space/punct/end
    )

    def _replace_spaced(m: re.Match[str]) -> str:
        word_part = m.group(1)
        digit = m.group(3)
        preceding = text[max(0, m.start() - 40) : m.start()]
        if _FOOTNOTE_LEGAL_CONTEXT.search(preceding):
            return m.group(0)
        if _CITATION_WORD.match(word_part):
            return m.group(0)
        # Protect numbered list items ("artículo 128") where digit > 2 chars
        # is already excluded by the \d{1,2} limit, but also protect when
        # the word looks like a legal citation target
        if int(digit) > 55:
            return m.group(0)
        return word_part

    text = word_space_digit.sub(_replace_spaced, text)

    # Pass 3: closing-paren/quote + spaced footnote — "INVEMAR) 13" → "INVEMAR)"
    paren_space_fn = re.compile(
        r"([)\]\u2019\u201D'\"])"  # closing bracket/quote
        r"(\s+)"
        r"(\d{1,2})"  # footnote marker
        r"(?=\s|[.,;:!?\)\]]|$)"
    )
    text = paren_space_fn.sub(r"\1", text)

    # Pass 4: year + trailing footnote digit — "20228" → "2022"
    year_digit = re.compile(r"\b((?:1[89]\d\d|20\d\d))(\d)\b(?!\d)")
    text = year_digit.sub(r"\1", text)

    # Pass 5: year/number + spaced footnote — "2021 32 ," → "2021,"
    year_space_fn = re.compile(
        r"(\b(?:1[89]\d\d|20\d\d))"  # 4-digit year
        r"(\s+)"
        r"(\d{1,2})"  # footnote marker
        r"(?=\s*[.,;:!?\)\]]|\s+[a-záéíóúüñ]|\s*$)"
    )
    text = year_space_fn.sub(r"\1", text)

    # Pass 6: hyphenated-code + spaced footnote — "CPT-CAM-012-21 34" → "CPT-CAM-012-21"
    code_space_fn = re.compile(
        r"(\b[A-Z][\w-]*-\d{2,4})"  # code ending in digits "CPT-CAM-012-21"
        r"(\s+)"
        r"(\d{1,2})"  # footnote marker
        r"(?=\s|[.,;:!?\)\]]|$)"
    )
    text = code_space_fn.sub(r"\1", text)

    return text


def _remove_repeated_blocks(text: str, min_occurrences: int = MIN_BLOCK_REPEATS) -> str:
    """Detect and remove repeated text blocks (headers/footers)."""
    paragraphs = text.split("\n\n")

    def _normalize(block: str) -> str:
        s = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", block)
        return s.strip()

    counts: Counter[str] = Counter(_normalize(p) for p in paragraphs if _normalize(p))
    repeated = {norm for norm, count in counts.items() if count >= min_occurrences}

    result: list[str] = []
    for p in paragraphs:
        norm = _normalize(p)
        if norm in repeated:
            continue
        result.append(p)

    return "\n\n".join(result)


def _relativize_image_refs(md_text: str, md_path: Path) -> str:
    """Convert absolute image paths produced by ``save_as_markdown`` to
    relative paths so the markdown stays portable.

    Docling emits ``![Image](C:\\abs\\path\\_artifacts\\img.png)`` when
    given an absolute ``md_path``.  This rewrites each ref to use only
    the path relative to the directory containing the ``.md`` file.
    """
    md_dir = md_path.parent

    def _rel(m: re.Match[str]) -> str:
        alt = m.group(1)
        raw_path = m.group(2)
        try:
            abs_img = Path(raw_path).resolve()
            rel = abs_img.relative_to(md_dir)
            rel_ref = rel.as_posix()
            if not rel_ref.startswith(("./", "../")):
                rel_ref = f"./{rel_ref}"
            return f"![{alt}]({rel_ref})"
        except (ValueError, OSError):
            return m.group(0)

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _rel, md_text)


def _filter_images(
    md_text: str,
    md_path: Path,
    min_pixels: int = MIN_IMAGE_PIXELS,
) -> str:
    """Filter out irrelevant images from markdown and delete their files."""
    md_dir = md_path.parent
    img_pattern = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

    def _resolve_image_path(img_ref: str) -> Path:
        cleaned_ref = img_ref.strip().strip("<>").strip("\"'")
        decoded_ref = unquote(cleaned_ref)
        candidates = [decoded_ref]
        candidates.append(unicodedata.normalize("NFC", decoded_ref))
        candidates.append(unicodedata.normalize("NFD", decoded_ref))

        seen: set[str] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                candidate_path = (md_dir / candidate).resolve()
            except OSError:
                continue
            if candidate_path.exists() and candidate_path.is_file():
                return candidate_path

        return (md_dir / decoded_ref).resolve()

    seen_hashes: set[str] = set()
    reason_counts: Counter[str] = Counter()
    analyzed: list[dict[str, object]] = []

    for match in img_pattern.finditer(md_text):
        img_ref = match.group(1)
        img_file = _resolve_image_path(img_ref)

        if not img_file.exists() or not img_file.is_file():
            continue

        try:
            with Image.open(img_file) as img:
                w, h = img.size
                area = w * h
                img_hash = hashlib.md5(img.tobytes()).hexdigest()
                gray = img.convert("L")
                pixels = list(gray.getdata())
        except Exception:
            continue

        remove_reason: str | None = None

        if w < min_pixels and h < min_pixels:
            remove_reason = "too_small"
        elif img_hash in seen_hashes:
            remove_reason = "duplicate_hash"
        else:
            seen_hashes.add(img_hash)

            if len(pixels) > 1 and statistics.variance(pixels) < IMAGE_LOW_VARIANCE:
                remove_reason = "low_variance"

            if remove_reason is None and IMAGE_REQUIRE_SEMANTIC_CONTEXT:
                pos = match.start()
                window_start = max(0, pos - IMAGE_CONTEXT_WINDOW)
                window_end = min(len(md_text), pos + IMAGE_CONTEXT_WINDOW)
                context = md_text[window_start:window_end]
                has_semantic_context = _IMAGE_CONTEXT_RE.search(context) is not None
                if not has_semantic_context and area < IMAGE_MIN_AREA_KEEP_WITHOUT_CONTEXT:
                    remove_reason = "no_semantic_context"

        analyzed.append(
            {
                "token": match.group(0),
                "file": img_file,
                "area": area,
                "remove_reason": remove_reason,
            }
        )

    if (
        IMAGE_FALLBACK_KEEP_ENABLED
        and analyzed
        and all(item["remove_reason"] is not None for item in analyzed)
    ):
        fallback_candidates = [
            item for item in analyzed if int(item["area"]) >= IMAGE_FALLBACK_MIN_AREA
        ]
        fallback_candidates.sort(key=lambda item: int(item["area"]), reverse=True)
        for item in fallback_candidates[: max(1, IMAGE_FALLBACK_MAX_KEEP)]:
            item["remove_reason"] = None
            item["fallback_reason"] = "fallback_keep_large"

    refs_to_remove: list[str] = []
    files_to_remove: list[Path] = []
    kept_count = 0

    for item in analyzed:
        fallback_reason = item.get("fallback_reason")
        if fallback_reason:
            reason_counts[str(fallback_reason)] += 1

        if item["remove_reason"] is None:
            kept_count += 1
            continue

        reason_counts[str(item["remove_reason"])] += 1
        refs_to_remove.append(str(item["token"]))
        files_to_remove.append(item["file"])

    for img_file in files_to_remove:
        img_file.unlink(missing_ok=True)

    logger.info(
        "Image filtering stats: total=%d kept=%d removed=%d reasons=%s",
        len(analyzed),
        kept_count,
        len(files_to_remove),
        dict(reason_counts),
    )

    for ref in refs_to_remove:
        md_text = md_text.replace(ref, "")

    return md_text


_HEADING_BODY_RE = re.compile(
    r"^(#{1,6}\s+"  # markdown heading prefix
    r"(?:"
    r"[IVXivx]+\."  # Roman numeral section "II."
    r"|"
    r"\d+(?:\.\d+)*\.?"  # Decimal section "1.1." / "2.3.1"
    r")?"
    r"\s*"
    r"[A-ZÁÉÍÓÚÜÑ][^.]*?"  # Title text (up to first period)
    r"\.)"  # Closing period of the title
    r"\s+"  # Whitespace gap
    r"([A-ZÁÉÍÓÚÜÑ]"  # Body starts with uppercase
    r"[A-Za-záéíóúüñÁÉÍÓÚÜÑ\s,()]{10,})"  # at least 10 chars of prose
)


def _split_heading_body(text: str) -> str:
    r"""Separate heading titles from body text that Docling fused onto the
    same ``## `` line.

    Colombian tribunal documents use section numbers like ``1.1.``,
    ``2.3.1.`` followed by a title, then the first body sentence.  Docling
    often joins them:

        ## 1.1. Posición de la parte demandante. En síntesis, ...

    This function detects the pattern and inserts a paragraph break after
    the heading title so downstream consumers see a clean heading.

    It also re-infers the first paragraph number that Docling absorbed into
    the heading.  For example, if ``2. Afirmó...`` follows the split body,
    the body is prepended with ``1.`` so the numbering sequence is complete.
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


def _maybe_prepend_number(body: str, lines: list[str], start_idx: int) -> str:
    """If the paragraphs following a split heading start at number N+1
    (e.g. ``2. Afirmó...``), prepend ``N.`` to *body* so the list is
    complete.  Docling absorbs the first list number into the heading's
    section number (``1.1.``), leaving the body without its ordinal.
    """
    next_num = _find_next_paragraph_number(lines, start_idx)
    if next_num is not None and next_num >= 2:
        expected = next_num - 1
        if not re.match(r"^\d+\.\s", body):
            body = f"{expected}. {body}"
    return body


def _find_next_paragraph_number(lines: list[str], start_idx: int) -> int | None:
    """Scan forward from *start_idx* for the first line that starts with a
    legal paragraph number (``N. ``).  Returns the number or ``None``.
    """
    for j in range(start_idx, min(start_idx + 15, len(lines))):
        m = re.match(r"^(\d{1,3})\.\s", lines[j])
        if m:
            return int(m.group(1))
    return None


def _clean_markdown(text: str) -> str:
    """Final structural cleanup of markdown."""
    text = _split_heading_body(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"([^\n])\n(#{1,6}\s)", r"\1\n\n\2", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text.strip() + "\n"


# ======================================================================
# DOCLING CONVERTER
# ======================================================================


def _build_converter() -> DocumentConverter:
    """Build configured Docling document converter for legal PDFs."""
    pipeline_options = PdfPipelineOptions()
    pipeline_options.images_scale = IMAGE_RESOLUTION_SCALE
    pipeline_options.generate_page_images = False
    pipeline_options.generate_picture_images = True
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


# ======================================================================
# MAIN CONVERSION PIPELINE
# ======================================================================


def convert_pdfs_to_markdown() -> list[Path]:
    """
    Convert all PDFs from data/raw/ to cleaned Markdown in data/bronze/.

    Full pipeline per PDF:
    1. Docling OCR conversion
    2. Initial Markdown extraction
    3. Legal document profiling
    4. Adaptive cleanup based on profile
    5. Semantic section segmentation
    6. Coastal entity extraction
    7. Quality evaluation
    8. Write final MD + JSON sidecars

    Returns list of generated .md files.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)

    pdf_paths = sorted(RAW_DIR.glob("*.pdf"))
    if not pdf_paths:
        print(f"No PDFs found in {RAW_DIR}")
        return []

    print(f"Found {len(pdf_paths)} PDF(s) in {RAW_DIR}")
    print("=" * 60)

    converter = _build_converter()
    generated: list[Path] = []

    for pdf_path in pdf_paths:
        print(f"\n📄 Processing: {pdf_path.name}")
        start = time.time()

        try:
            # Step 1: Docling conversion
            conv_result = converter.convert(pdf_path)

            # Step 2: Initial markdown extraction.
            # Keep ``{stem}.md`` at bronze root while writing image
            # artifacts under ``{stem}/assets`` next to it.
            doc_stem = pdf_path.stem
            doc_dir = BRONZE_DIR / doc_stem
            assets_dir = doc_dir / "assets"
            doc_dir.mkdir(parents=True, exist_ok=True)
            md_path = (BRONZE_DIR / f"{doc_stem}.md").resolve()
            conv_result.document.save_as_markdown(
                md_path,
                artifacts_dir=assets_dir,
                image_mode=ImageRefMode.REFERENCED,
            )

            original_md = md_path.read_text(encoding="utf-8")
            original_md = _relativize_image_refs(original_md, md_path)

            # Step 3: Document profiling
            profile = profile_legal_document(original_md)

            # Step 4: Adaptive cleanup
            cleaned_md = adaptive_cleanup(original_md, profile, md_path)

            # Step 5: Semantic segmentation
            blocks = segment_legal_sections(cleaned_md)

            # Step 6: Coastal entity extraction
            entities = extract_coastal_legal_entities(cleaned_md)

            # Step 7: Quality evaluation
            elapsed = time.time() - start
            quality = evaluate_document_quality(original_md, cleaned_md, blocks, entities, profile)
            quality.processing_time_seconds = elapsed

            # Step 8: Write outputs
            md_path.write_text(cleaned_md, encoding="utf-8")

            quality_path = doc_dir / f"{doc_stem}.quality.json"
            quality_path.write_text(
                json.dumps(asdict(quality), indent=2, ensure_ascii=False), encoding="utf-8"
            )

            if entities:
                entities_path = doc_dir / f"{doc_stem}.entities.json"
                entities_path.write_text(
                    json.dumps(entities, indent=2, ensure_ascii=False), encoding="utf-8"
                )

            # Print summary
            print(f"   ⏱️  Time: {elapsed:.1f}s")
            print(f"   📊 Quality: {quality.final_quality:.1f}%")
            print(f"   📑 Sections: {dict(quality.section_counts)}")
            print(f"   🏖️  Coastal entities: {quality.entity_count}")
            print(f"   ✅ Output: {md_path.name}")

            generated.append(md_path)

        except Exception as e:
            logger.error(f"Failed to process {pdf_path.name}: {e}")
            print(f"   ❌ Error: {e}")
            continue

    print("\n" + "=" * 60)
    print(f"Conversion complete: {len(generated)}/{len(pdf_paths)} files in {BRONZE_DIR}")

    return generated


# ======================================================================
# ALTERNATIVE PIPELINE FOR SINGLE DOCUMENT
# ======================================================================


def process_single_pdf(
    pdf_path: Path,
    output_dir: Path | None = None,
) -> tuple[Path, DocumentQualityReport] | None:
    """
    Process a single PDF through the full pipeline.

    Args:
        pdf_path: Path to input PDF
        output_dir: Output directory (defaults to BRONZE_DIR)

    Returns:
        Tuple of (output_md_path, quality_report) or None on failure
    """
    output_dir = output_dir or BRONZE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    converter = _build_converter()
    start = time.time()

    try:
        conv_result = converter.convert(pdf_path)

        doc_stem = pdf_path.stem
        doc_dir = output_dir / doc_stem
        assets_dir = doc_dir / "assets"
        doc_dir.mkdir(parents=True, exist_ok=True)
        md_path = (output_dir / f"{doc_stem}.md").resolve()
        conv_result.document.save_as_markdown(
            md_path,
            artifacts_dir=assets_dir,
            image_mode=ImageRefMode.REFERENCED,
        )

        original_md = md_path.read_text(encoding="utf-8")
        original_md = _relativize_image_refs(original_md, md_path)
        profile = profile_legal_document(original_md)
        cleaned_md = adaptive_cleanup(original_md, profile, md_path)
        blocks = segment_legal_sections(cleaned_md)
        entities = extract_coastal_legal_entities(cleaned_md)

        elapsed = time.time() - start
        quality = evaluate_document_quality(original_md, cleaned_md, blocks, entities, profile)
        quality.processing_time_seconds = elapsed

        md_path.write_text(cleaned_md, encoding="utf-8")

        quality_path = doc_dir / f"{doc_stem}.quality.json"
        quality_path.write_text(
            json.dumps(asdict(quality), indent=2, ensure_ascii=False), encoding="utf-8"
        )

        if entities:
            entities_path = doc_dir / f"{doc_stem}.entities.json"
            entities_path.write_text(
                json.dumps(entities, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        return md_path, quality

    except Exception as e:
        logger.error(f"Failed to process {pdf_path}: {e}")
        return None


# ======================================================================
# Entry-point
# ======================================================================


def main() -> None:
    """Main entry point for CLI execution."""
    convert_pdfs_to_markdown()


if __name__ == "__main__":
    main()
