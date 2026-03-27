# src/ingest/pdf_to_md.py

from __future__ import annotations

import hashlib
import logging
import re
import statistics
import time
import warnings
from collections import Counter
from pathlib import Path

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
MIN_BLOCK_REPEATS = 2          # ≥ 2 occurrences triggers repeated-block removal
NOISE_CHAR_RATIO = 0.45        # fraction of non-alphanum chars that marks a line as noise
IMAGE_LOW_VARIANCE = 100.0     # grayscale pixel variance below which an image is discarded
IMAGE_CONTEXT_WINDOW = 300     # chars around an image reference searched for semantic words

# ------------------------------------------------------------------
# OCR correction table
# ------------------------------------------------------------------
# Each entry is (compiled_pattern, replacement).  Ordered from most
# specific to least specific so that broader patterns do not shadow
# narrower ones.

_OCR_CORRECTIONS: list[tuple[re.Pattern[str], str]] = [
    # "ción" / "ciones" — the most common accented suffix in Spanish
    (re.compile(r'ci6nes\b'), 'ciones'),
    (re.compile(r'ci6n\b'), 'ción'),
    # Generic "Xón" / "Xós" where X is a letter (catches ión, ución, etc.)
    (re.compile(r'([A-Za-záéíóúüñÁÉÍÓÚÜÑ])6n\b'), r'\1ón'),
    (re.compile(r'([A-Za-záéíóúüñÁÉÍÓÚÜÑ])6s\b'), r'\1ós'),
    # Digit 6 sandwiched between two lowercase letters → ó
    (re.compile(r'([a-záéíóúüñ])6([a-záéíóúüñ])'), r'\1ó\2'),
]

# ------------------------------------------------------------------
# Header / footer keyword set
# ------------------------------------------------------------------

_HEADER_FOOTER_KEYWORDS: frozenset[str] = frozenset({
    'radicación', 'radicacion',
    'tribunal', 'expediente',
    'magistrado', 'magistrada',
    'pág.', 'página', 'pagina',
    'sala', 'consejo de estado',
    'juzgado', 'sentencia',
    'república de colombia', 'republica de colombia',
})

# ------------------------------------------------------------------
# Internal-reference patterns (line-level)
# ------------------------------------------------------------------

_INTERNAL_REF_PATTERNS: list[re.Pattern[str]] = [
    # ── page / folio references ────────────────────────────────────────────
    # Optional leading footnote number: "3 Ver págs. 2-6..." or "Ver págs. 2-6..."
    re.compile(r'(?i)^\s*\d{0,2}\s*ver\s+p[aá]gs?\.?\s*\d'),
    re.compile(r'(?i)^\s*\d{0,2}\s*ver\s+considerando\b'),
    re.compile(r'(?i)^\s*p[aá]g[s.]?\s*\d+\s*[-–]\s*\d+\s*$'),
    re.compile(r'(?i)^\s*folio[s]?\s+\d+'),
    re.compile(r'(?i)^\s*cuaderno\s+\d+'),
    re.compile(r'(?i)\barchivo\s+\S+\.pdf\b'),
    re.compile(r'(?i)^\s*expediente\s+n[°º]?\s*\d'),
    re.compile(r'(?i)^\s*p[aá]g\.?\s*\d+\s*$'),             # bare "Pág. 12" lines

    # ── footnote body lines — PDF / OneDrive references ────────────────────
    re.compile(r'(?i)^\s*\d{0,2}\s*ver\s+pdf\b'),            # "9 Ver PDF 50..."
    re.compile(r'(?i)\bver\s+pdf\s*:?\s*\d+\b'),              # "Ver PDF: 17 del..."
    re.compile(r'(?i)^\s*\d{1,2}\s+https?://'),               # "33 https://..."
    re.compile(r'(?i)^\s*\d{1,2}\s+escuchar\b'),

    # ── numbered footnote body lines — common legal-citation starters ───────
    # "1 En adelante DIMAR" / "2 En adelante DADSA"
    re.compile(r'(?i)^\s*\d{1,2}\s+en adelante\b'),
    # "15 Al respecto ver: Consejo de Estado..."
    re.compile(r'(?i)^\s*\d{1,2}\s+al respecto\b'),
    # "31 Corte Constitucional..." / "40 Consejo De Estado..." / "41 Sección Primera..."
    re.compile(r'(?i)^\s*\d{1,2}\s+(corte constitucional|consejo de estado|sección primera|sala plena)\b'),
    # "32 Vale la pena anotar que..."
    re.compile(r'(?i)^\s*\d{1,2}\s+vale la pena\b'),
    # "16 Presentación de la demanda: 21 de julio de 2016..."
    re.compile(r'(?i)^\s*\d{1,2}\s+presentación de la demanda\b'),
    # "38 T-519 de 1992..." / "39 SU-540 de 2007..."
    re.compile(r'(?i)^\s*\d{1,2}\s+[A-Za-z]{1,3}-\d{3,}\b'),
    # "37 M.P. Álvaro Tafur Galvis"
    re.compile(r'(?i)^\s*\d{1,2}\s+m\.p\.\b'),
]

# ------------------------------------------------------------------
# Footnote-number protection: legal context words
# ------------------------------------------------------------------
# If any of these words appear in the 40 characters *before* a
# word+digit match, the digit is kept (it is part of a legal citation,
# not a footnote marker).

_FOOTNOTE_LEGAL_CONTEXT: re.Pattern[str] = re.compile(
    r'(?i)(ley|artículo|articulo|decreto|numeral|inciso|parágrafo'
    r'|paragrafo|literal|ordinal|resolución|resolucion)\s*$'
)

# ------------------------------------------------------------------
# Semantic image-context words
# ------------------------------------------------------------------

_IMAGE_CONTEXT_RE: re.Pattern[str] = re.compile(
    r'(?i)\b(figura|tabla|imagen|gráfico|grafico|ilustración'
    r'|ilustracion|foto|fotografía|fotografia|esquema|diagrama)\b'
)

# ------------------------------------------------------------------
# Markdown structure line detector (used in noise filter)
# ------------------------------------------------------------------

_MD_STRUCTURE_RE: re.Pattern[str] = re.compile(
    r'^\s*(#{1,6}\s|[-*|!]|\d+\.|---)'
)

# ------------------------------------------------------------------
# Rutas absolutas derivadas de la ubicación del archivo
# ------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"


# ======================================================================
# Post-processing pipeline — step functions
# ======================================================================


def _fix_ocr_chars(text: str) -> str:
    """Corrige artefactos OCR comunes en documentos jurídicos españoles.

    Aplica la tabla ``_OCR_CORRECTIONS`` de más específica a menos
    específica.  Solo corrige patrones inequívocos (dígito rodeado de
    letras) para no alterar números legales ni años.

    Las referencias a imágenes Markdown (``![...](...)``) se protegen
    antes de aplicar las correcciones y se restauran después, evitando
    que los hashes hexadecimales de los nombres de archivo se corrompan.
    """
    # Tokenise: split text into alternating [plain, image_ref, plain, ...]
    img_token_re = re.compile(r'(!\[[^\]]*\]\([^)]+\))')
    parts = img_token_re.split(text)

    result_parts: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Odd indices are the captured image reference tokens — leave untouched
            result_parts.append(part)
        else:
            for pattern, replacement in _OCR_CORRECTIONS:
                part = pattern.sub(replacement, part)
            result_parts.append(part)

    return ''.join(result_parts)


def _remove_noisy_lines(text: str, noise_ratio: float = NOISE_CHAR_RATIO) -> str:
    """Elimina líneas con alto porcentaje de caracteres no lingüísticos.

    Por cada línea calcula:  non_linguistic_chars / total_chars.
    Si la proporción supera ``noise_ratio`` la línea se descarta.
    Las líneas de estructura Markdown (headings, tablas, imágenes,
    separadores) se preservan siempre independientemente del ratio.
    """
    cleaned: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue
        if _MD_STRUCTURE_RE.match(stripped):
            cleaned.append(line)
            continue
        non_linguistic = sum(
            1 for c in stripped if not c.isalnum() and not c.isspace()
        )
        if non_linguistic / len(stripped) < noise_ratio:
            cleaned.append(line)
    return '\n'.join(cleaned)


def _reconstruct_paragraphs(text: str) -> str:
    """Reconstruye párrafos cortados por saltos de página.

    Dos pasadas:

    1. **Guión de partición**: une palabras cortadas al final de línea
       (``pal-\\nabra`` → ``palabra``).
    2. **Párrafo suave**: si un párrafo no termina en ``. : ; ? !`` y
       el siguiente comienza en minúscula (y no es un heading ni lista),
       los une con un espacio en lugar de ``\\n\\n``.
    """
    # Pass 1: rejoin hyphenated word breaks
    text = re.sub(
        r'([A-Za-záéíóúüñÁÉÍÓÚÜÑ])-\n([a-záéíóúüñ])',
        r'\1\2',
        text,
    )

    # Pass 2: join across paragraph boundaries
    paragraphs = text.split('\n\n')
    result: list[str] = []
    i = 0
    while i < len(paragraphs):
        current = paragraphs[i]
        stripped_current = current.strip()

        if i + 1 < len(paragraphs):
            next_para = paragraphs[i + 1]
            stripped_next = next_para.strip()

            last_char = stripped_current[-1] if stripped_current else ''
            first_char = stripped_next[0] if stripped_next else ''

            ends_without_terminator = last_char not in '.;:?!'
            next_starts_lower = bool(first_char) and first_char.islower()
            current_is_heading = stripped_current.startswith('#')
            next_is_special = stripped_next.startswith(('#', '-', '*')) or (
                len(stripped_next) > 1
                and stripped_next[0].isdigit()
                and stripped_next[1] == '.'
            )

            if (
                ends_without_terminator
                and next_starts_lower
                and not current_is_heading
                and not next_is_special
            ):
                result.append(stripped_current + ' ' + stripped_next)
                i += 2
                continue

        result.append(current)
        i += 1

    return '\n\n'.join(result)


def _remove_footnote_numbers(text: str) -> str:
    """Elimina números de notas al pie pegados al final de palabras.

    Patrón objetivo: ``palabra1``, ``DIMAR2`` — letras (≥ 2) seguidas
    directamente de **un solo dígito** sin espacio, al final de palabra.

    Protecciones:
    - Años de cuatro dígitos: nunca coincidirán (``(?!\\d)`` + único dígito).
    - Palabras legales en los 40 caracteres previos: ley, artículo,
      decreto, numeral, inciso, parágrafo, literal, ordinal,
      resolución → el número se conserva.
    """
    # Words that ARE themselves legal citation terms (e.g. "artículo", "decreto").
    # When the matched word is one of these, the trailing digit is likely an article
    # number written without a space — leave it untouched.
    _CITATION_WORD = re.compile(
        r'(?i)^(ley|artículo|articulo|decreto|numeral|inciso|parágrafo'
        r'|paragrafo|literal|ordinal|resolución|resolucion)$'
    )

    # Pass 1: word + 1–2 trailing digits  (e.g. "DIMAR2", "jurisdicción14")
    word_digit = re.compile(
        r'([A-Za-záéíóúüñÁÉÍÓÚÜÑ]{2,})(\d{1,2})\b(?!\d)',
        re.UNICODE,
    )

    def _replace_word(m: re.Match[str]) -> str:
        word_part = m.group(1)
        preceding = text[max(0, m.start() - 40) : m.start()]
        # Protect: preceding context ends with a legal reference word
        if _FOOTNOTE_LEGAL_CONTEXT.search(preceding):
            return m.group(0)
        # Protect: the word itself is a legal citation term (e.g. "artículo14"
        # where 14 could be the actual article number written without a space)
        if _CITATION_WORD.match(word_part):
            return m.group(0)
        return word_part

    text = word_digit.sub(_replace_word, text)

    # Pass 2: 4-digit year immediately followed by a single footnote digit
    # e.g. "20228" = year 2022 + footnote marker 8
    year_digit = re.compile(r'\b((?:1[89]\d\d|20\d\d))(\d)\b(?!\d)')
    text = year_digit.sub(r'\1', text)

    return text


def _remove_internal_references(text: str) -> str:
    """Elimina líneas que contienen referencias internas al expediente.

    Detecta y descarta líneas que coincidan con alguno de los patrones
    en ``_INTERNAL_REF_PATTERNS``:
    - ``Ver pags. 2-6…`` / ``Ver PDF 50…``
    - Referencias a folios, cuadernos y archivos PDF
    - Líneas que son solo un número de página (``Pág. 12``)
    - Encabezados de expediente como línea aislada

    También elimina el prefijo ``pág. N`` al inicio de líneas de
    continuación (artefacto OCR donde el número de página impreso en el
    documento queda adherido al texto que prosigue en esa página).
    """
    # Strip inline "pág. N" prefixes that precede continuation text.
    # Only removes the prefix when it is followed by a lowercase letter
    # (i.e. the text continues — not a proper noun or chapter heading).
    text = re.sub(
        r'(?im)^\s*p[aá]g\.?\s*\d+\s+(?=[a-záéíóúüñ])',
        '',
        text,
    )

    lines = text.splitlines()
    cleaned = [
        line
        for line in lines
        if not any(p.search(line) for p in _INTERNAL_REF_PATTERNS)
    ]
    return '\n'.join(cleaned)


def _clean_markdown(text: str) -> str:
    """Limpieza estructural del Markdown.

    Normaliza saltos de línea excesivos, asegura separación antes de
    headings y elimina espacios/tabulaciones al final de línea.
    """
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"([^\n])\n(#{1,6}\s)", r"\1\n\n\2", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text.strip() + "\n"


def _remove_repeated_blocks(text: str, min_occurrences: int = MIN_BLOCK_REPEATS) -> str:
    """Detecta y elimina bloques de texto repetidos (encabezados/pies de página).

    Elimina bloques que aparecen ``≥ min_occurrences`` veces (umbral = 2
    para mayor sensibilidad).  La comparación normaliza las referencias a
    imágenes para que bloques idénticos salvo por el nombre del fichero de
    imagen se reconozcan como duplicados.
    """
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


def _filter_images(
    md_text: str,
    md_path: Path,
    min_pixels: int = MIN_IMAGE_PIXELS,
) -> str:
    """Elimina imágenes irrelevantes del Markdown y borra sus archivos.

    Criterios de eliminación (aplicados en orden):

    1. **Tamaño mínimo**: ambas dimensiones < ``min_pixels`` (íconos,
       sellos, viñetas).
    2. **Duplicados**: mismo hash MD5 de contenido de píxeles.
    3. **Baja varianza**: imagen casi uniforme (fondo blanco, marca de
       agua).  Calculado en escala de grises con ``statistics.variance``
       sobre todos los píxeles; umbral ``IMAGE_LOW_VARIANCE``.
    4. **Sin contexto semántico**: ninguna palabra clave de figura/tabla
       aparece en las ``IMAGE_CONTEXT_WINDOW`` caracteres adyacentes a
       la referencia en el Markdown.
    """
    md_dir = md_path.parent
    img_pattern = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

    seen_hashes: set[str] = set()
    refs_to_remove: list[str] = []

    for match in img_pattern.finditer(md_text):
        img_ref = match.group(1)
        img_file = (md_dir / img_ref).resolve()

        if not img_file.exists() or not img_file.is_file():
            continue

        try:
            with Image.open(img_file) as img:
                w, h = img.size
                img_hash = hashlib.md5(img.tobytes()).hexdigest()
                gray = img.convert("L")
                pixels = list(gray.getdata())
        except Exception:
            continue

        should_remove = False

        if w < min_pixels and h < min_pixels:
            should_remove = True
        elif img_hash in seen_hashes:
            should_remove = True
        else:
            seen_hashes.add(img_hash)

            # Criterion 3: low pixel variance → nearly uniform image
            if len(pixels) > 1 and statistics.variance(pixels) < IMAGE_LOW_VARIANCE:
                should_remove = True

            # Criterion 4: no semantic context word nearby
            if not should_remove:
                pos = match.start()
                window_start = max(0, pos - IMAGE_CONTEXT_WINDOW)
                window_end = min(len(md_text), pos + IMAGE_CONTEXT_WINDOW)
                context = md_text[window_start:window_end]
                if not _IMAGE_CONTEXT_RE.search(context):
                    should_remove = True

        if should_remove:
            refs_to_remove.append(match.group(0))
            img_file.unlink(missing_ok=True)

    for ref in refs_to_remove:
        md_text = md_text.replace(ref, "")

    return md_text


# ======================================================================
# Conversión PDF → Markdown
# ======================================================================


def _build_converter() -> DocumentConverter:
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


def convert_pdfs_to_markdown() -> list[Path]:
    """Convierte todos los PDFs de data/raw/ a Markdown limpio en data/bronze/.

    Flujo por cada PDF:

    1. Docling convierte el PDF (OCR, tablas e imágenes).
    2. ``save_as_markdown`` escribe el ``.md`` y las imágenes referenciadas.
    3. Pipeline de post-procesado (en orden):

       1. ``_fix_ocr_chars``              — corrección de artefactos OCR
       2. ``_remove_noisy_lines``         — eliminación de líneas con ruido
       3. ``_remove_internal_references`` — referencias a páginas/folios (antes de unir párrafos)
       4. ``_reconstruct_paragraphs``     — reconstrucción de párrafos cortados
       5. ``_remove_footnote_numbers``    — eliminación de marcadores de nota
       6. ``_remove_repeated_blocks``     — encabezados y pies repetidos
       7. ``_filter_images``              — filtrado por tamaño/varianza/contexto
       8. ``_clean_markdown``             — limpieza estructural final

    Devuelve la lista de archivos ``.md`` generados.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)

    pdf_paths = sorted(RAW_DIR.glob("*.pdf"))
    if not pdf_paths:
        print(f"No se encontraron PDFs en {RAW_DIR}")
        return []

    print(f"Encontrados {len(pdf_paths)} PDF(s) en {RAW_DIR}")
    converter = _build_converter()
    generated: list[Path] = []

    for pdf_path in pdf_paths:
        print(f"Convirtiendo: {pdf_path.name}")
        start = time.time()

        conv_result = converter.convert(pdf_path)

        md_path = BRONZE_DIR / f"{pdf_path.stem}.md"
        conv_result.document.save_as_markdown(
            md_path,
            image_mode=ImageRefMode.REFERENCED,
        )

        md_text = md_path.read_text(encoding="utf-8")
        md_text = _fix_ocr_chars(md_text)
        md_text = _remove_noisy_lines(md_text)
        md_text = _remove_internal_references(md_text)  # before paragraph join
        md_text = _reconstruct_paragraphs(md_text)
        md_text = _remove_footnote_numbers(md_text)
        md_text = _remove_repeated_blocks(md_text)
        md_text = _filter_images(md_text, md_path)
        md_text = _clean_markdown(md_text)
        md_path.write_text(md_text, encoding="utf-8")

        elapsed = time.time() - start
        print(f"  -> {md_path}  ({elapsed:.1f}s)")
        generated.append(md_path)

    print(f"Conversión completada: {len(generated)} archivo(s) en {BRONZE_DIR}")
    return generated


# ======================================================================
# Entry-point
# ======================================================================


def main() -> None:
    convert_pdfs_to_markdown()


if __name__ == "__main__":
    main()
