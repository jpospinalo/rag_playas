"""
Tuneable constants, shared regex patterns, OCR correction table, and
directory paths for the PDF-to-Markdown pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path

# ------------------------------------------------------------------
# Image processing
# ------------------------------------------------------------------

IMAGE_RESOLUTION_SCALE = 2.0
MIN_IMAGE_PIXELS = 350
IMAGE_LOW_VARIANCE = 100.0
IMAGE_CONTEXT_WINDOW = 300
IMAGE_REQUIRE_SEMANTIC_CONTEXT = True
IMAGE_MIN_AREA_KEEP_WITHOUT_CONTEXT = 250_000
IMAGE_FALLBACK_KEEP_ENABLED = True
IMAGE_FALLBACK_MAX_KEEP = 2
IMAGE_FALLBACK_MIN_AREA = 160_000

# ------------------------------------------------------------------
# Text cleanup
# ------------------------------------------------------------------

MIN_BLOCK_REPEATS = 2
NOISE_CHAR_RATIO = 0.45

# ------------------------------------------------------------------
# Document profiling thresholds
# ------------------------------------------------------------------

LEGAL_DENSITY_THRESHOLD = 0.15
FOOTNOTE_DENSITY_THRESHOLD = 0.10
OCR_NOISE_THRESHOLD = 0.05
REPEATED_FURNITURE_THRESHOLD = 0.60
COASTAL_DENSITY_THRESHOLD = 0.02

# ------------------------------------------------------------------
# Internal reference scoring
# ------------------------------------------------------------------

INTERNAL_REF_SCORE_THRESHOLD = 3

# ------------------------------------------------------------------
# OCR correction table
# ------------------------------------------------------------------

OCR_CORRECTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ci6nes\b"), "ciones"),
    (re.compile(r"ci6n\b"), "ción"),
    (re.compile(r"([A-Za-záéíóúüñÁÉÍÓÚÜÑ])6n\b"), r"\1ón"),
    (re.compile(r"([A-Za-záéíóúüñÁÉÍÓÚÜÑ])6s\b"), r"\1ós"),
    (re.compile(r"([a-záéíóúüñ])6([a-záéíóúüñ])"), r"\1ó\2"),
    (re.compile(r"\b0([a-záéíóúüñ])"), r"o\1"),
    (re.compile(r"([a-záéíóúüñ])0\b"), r"\1o"),
    (re.compile(r"\bl([0O])s\b"), "los"),
    (re.compile(r"\bd([0O])s\b"), "dos"),
    (re.compile(r"(?i)\bpr([0O])ceso\b"), "proceso"),
    (re.compile(r"(?i)\bc([0O])nsejo\b"), "consejo"),
]

# ------------------------------------------------------------------
# Shared regex patterns
# ------------------------------------------------------------------

MD_STRUCTURE_RE: re.Pattern[str] = re.compile(r"^\s*(#{1,6}\s|[-*|!]|\d+\.|---)")

FOOTNOTE_LEGAL_CONTEXT: re.Pattern[str] = re.compile(
    r"(?i)(ley|artículo|articulo|decreto|numeral|inciso|parágrafo"
    r"|paragrafo|literal|ordinal|resolución|resolucion)\s*$"
)

IMAGE_CONTEXT_RE: re.Pattern[str] = re.compile(
    r"(?i)\b(figura|tabla|imagen|gráfico|grafico|ilustración"
    r"|ilustracion|foto|fotografía|fotografia|esquema|diagrama"
    r"|mapa|mapas|plano|planos|croquis|anexo|anexos|cronograma"
    r"|fase|fases)\b"
)

# Coastal/beach law semantic terms used across profiling and segmentation
COASTAL_TERMS: list[str] = [
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

COASTAL_PATTERN: re.Pattern[str] = re.compile(
    r"(?i)\b(" + "|".join(re.escape(t) for t in COASTAL_TERMS) + r")\b"
)

# ------------------------------------------------------------------
# Directory paths
# ------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # project root
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
