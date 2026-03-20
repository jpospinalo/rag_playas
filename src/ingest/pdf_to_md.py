# src/ingest/pdf_to_md.py

from __future__ import annotations

import logging
import re
import time
import warnings
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import ImageRefMode, PictureItem, TableItem

warnings.filterwarnings("ignore", category=FutureWarning)

logging.getLogger("docling").setLevel(logging.WARNING)
logging.getLogger("rapidocr").setLevel(logging.WARNING)
logging.getLogger("onnxruntime").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

IMAGE_RESOLUTION_SCALE = 2.0

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
IMAGES_DIR = BRONZE_DIR / "images"


# ---------------------------------------------------------------------
# Post-procesado del Markdown
# ---------------------------------------------------------------------

def _clean_markdown(text: str) -> str:
    """Limpieza ligera del Markdown generado por Docling."""
    # Colapsar 3+ líneas en blanco consecutivas a 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Asegurar línea en blanco antes de encabezados
    text = re.sub(r"([^\n])\n(#{1,6}\s)", r"\1\n\n\2", text)
    # Eliminar espacios al final de cada línea
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text.strip() + "\n"


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


def _save_element_images(conv_result, doc_stem: str) -> None:
    """Guarda imágenes de figuras y tablas como PNG en IMAGES_DIR."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    table_counter = 0
    picture_counter = 0

    for element, _level in conv_result.document.iterate_items():
        if isinstance(element, TableItem):
            img = element.get_image(conv_result.document)
            if img is None:
                continue
            table_counter += 1
            img_path = IMAGES_DIR / f"{doc_stem}-table-{table_counter}.png"
            with img_path.open("wb") as fp:
                img.save(fp, "PNG")

        if isinstance(element, PictureItem):
            img = element.get_image(conv_result.document)
            if img is None:
                continue
            picture_counter += 1
            img_path = IMAGES_DIR / f"{doc_stem}-picture-{picture_counter}.png"
            with img_path.open("wb") as fp:
                img.save(fp, "PNG")

    if table_counter or picture_counter:
        print(f"  Imágenes guardadas: {picture_counter} figuras, {table_counter} tablas")


def convert_pdfs_to_markdown() -> list[Path]:
    """
    Convierte todos los PDFs de data/raw/ a Markdown limpio en data/bronze/.

    Las imágenes se guardan en data/bronze/images/ y se referencian
    en el Markdown resultante.

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
        doc_stem = pdf_path.stem

        _save_element_images(conv_result, doc_stem)

        md_path = BRONZE_DIR / f"{doc_stem}.md"
        conv_result.document.save_as_markdown(
            md_path,
            image_mode=ImageRefMode.REFERENCED,
        )

        md_text = md_path.read_text(encoding="utf-8")
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
