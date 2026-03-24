# src/ingest/pdf_to_md.py

from __future__ import annotations

import hashlib
import logging
import re
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

IMAGE_RESOLUTION_SCALE = 2.0
MIN_IMAGE_PIXELS = 350
MIN_BLOCK_REPEATS = 3

# Rutas absolutas derivadas de la ubicación del archivo
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"


# ---------------------------------------------------------------------
# Post-procesado del Markdown
# ---------------------------------------------------------------------

def _clean_markdown(text: str) -> str:
    """Limpieza ligera del Markdown generado por Docling."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"([^\n])\n(#{1,6}\s)", r"\1\n\n\2", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text.strip() + "\n"


def _remove_repeated_blocks(text: str, min_occurrences: int = MIN_BLOCK_REPEATS) -> str:
    """
    Detecta y elimina bloques de texto (párrafos) que se repiten
    múltiples veces en el documento, típicos de encabezados y pies
    de página en documentos jurídicos.

    La comparación ignora referencias a imágenes para que bloques
    idénticos salvo por el nombre de archivo de la imagen se
    reconozcan como duplicados.
    """
    paragraphs = text.split("\n\n")

    def _normalize(block: str) -> str:
        s = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", block)
        return s.strip()

    counts: Counter[str] = Counter()
    for p in paragraphs:
        norm = _normalize(p)
        if norm:
            counts[norm] += 1

    repeated = {norm for norm, count in counts.items() if count >= min_occurrences}

    result: list[str] = []
    for p in paragraphs:
        if _normalize(p) in repeated:
            continue
        result.append(p)

    return "\n\n".join(result)


def _filter_images(
    md_text: str,
    md_path: Path,
    min_pixels: int = MIN_IMAGE_PIXELS,
) -> str:
    """
    Elimina imágenes pequeñas (íconos, símbolos) y duplicadas.

    Recorre las referencias a imágenes en el Markdown, abre cada archivo,
    y descarta las que sean menores a min_pixels en ambas dimensiones o
    que tengan el mismo hash de contenido que una imagen ya vista.
    Borra el archivo y su referencia en el Markdown.
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
        except Exception:
            continue

        should_remove = False
        if w < min_pixels and h < min_pixels:
            should_remove = True
        elif img_hash in seen_hashes:
            should_remove = True
        else:
            seen_hashes.add(img_hash)

        if should_remove:
            refs_to_remove.append(match.group(0))
            img_file.unlink(missing_ok=True)

    for ref in refs_to_remove:
        md_text = md_text.replace(ref, "")

    return md_text


# ---------------------------------------------------------------------
# Conversión PDF → Markdown
# ---------------------------------------------------------------------

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
    """
    Convierte todos los PDFs de data/raw/ a Markdown limpio en data/bronze/.

    Flujo por cada PDF:
      1) Docling convierte el PDF (con OCR, tablas e imágenes).
      2) save_as_markdown guarda el .md y las imágenes referenciadas.
      3) Post-procesado:
         a) Limpieza de formato Markdown.
         b) Eliminación de bloques repetidos (encabezados / pies de página).
         c) Filtrado de imágenes pequeñas (íconos) y duplicadas.

    Devuelve la lista de archivos .md generados.
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
        md_text = _clean_markdown(md_text)
        md_text = _remove_repeated_blocks(md_text)
        md_text = _filter_images(md_text, md_path)
        md_text = _clean_markdown(md_text)
        md_path.write_text(md_text, encoding="utf-8")

        elapsed = time.time() - start
        print(f"  -> {md_path}  ({elapsed:.1f}s)")
        generated.append(md_path)

    print(f"Conversión completada: {len(generated)} archivo(s) en {BRONZE_DIR}")
    return generated


# ---------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------

def main() -> None:
    convert_pdfs_to_markdown()


if __name__ == "__main__":
    main()
