"""
Main PDF-to-Markdown conversion pipeline.

Orchestrates Docling OCR, document profiling, adaptive cleanup, semantic
segmentation, entity extraction, quality evaluation, and file output.
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
import warnings
from dataclasses import asdict
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import ImageRefMode

from ..s3_client import download_file, list_keys, upload_directory, upload_file
from .cleaner import adaptive_cleanup
from .config import BRONZE_PREFIX, IMAGE_RESOLUTION_SCALE, RAW_PREFIX
from .images import relativize_image_refs
from .models import DocumentQualityReport
from .profiler import profile_legal_document
from .quality import evaluate_document_quality
from .segmenter import extract_coastal_legal_entities, segment_legal_sections

warnings.filterwarnings("ignore", category=FutureWarning)

logging.getLogger("docling").setLevel(logging.WARNING)
logging.getLogger("rapidocr").setLevel(logging.WARNING)
logging.getLogger("onnxruntime").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


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


def _run_pipeline(
    pdf_path: Path,
    output_dir: Path,
    converter: DocumentConverter,
) -> tuple[Path, DocumentQualityReport]:
    """Run the full processing pipeline for a single PDF (local paths only).

    Returns (md_path, quality_report).  Raises on failure.
    """
    start = time.time()

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
    original_md = relativize_image_refs(original_md, md_path)

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


def convert_pdfs_to_markdown() -> list[str]:
    """Convierte todos los PDFs de S3 raw/ a Markdown limpio en S3 bronze/.

    Estrategia:
    1. Lista los PDFs en S3 raw/.
    2. Descarga cada PDF a un directorio temporal.
    3. Procesa con Docling (_run_pipeline) localmente.
    4. Sube el .md y los sidecars (assets/, quality.json, entities.json) a S3 bronze/.

    Devuelve la lista de S3 keys de los archivos .md generados.
    """
    pdf_keys = list_keys(RAW_PREFIX, suffix=".pdf")
    if not pdf_keys:
        print(f"No PDFs found in s3://{RAW_PREFIX}")
        return []

    print(f"Found {len(pdf_keys)} PDF(s) in s3://{RAW_PREFIX}")
    print("=" * 60)

    converter = _build_converter()
    generated: list[str] = []

    with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as bronze_tmp:
        raw_tmp_path = Path(raw_tmp)
        bronze_tmp_path = Path(bronze_tmp)

        for pdf_key in pdf_keys:
            pdf_name = pdf_key.split("/")[-1]
            local_pdf = raw_tmp_path / pdf_name

            print(f"\nProcessing: {pdf_name}")
            download_file(pdf_key, str(local_pdf))

            try:
                md_path, quality = _run_pipeline(local_pdf, bronze_tmp_path, converter)

                print(f"   Time: {quality.processing_time_seconds:.1f}s")
                print(f"   Quality: {quality.final_quality:.1f}%")
                print(f"   Sections: {dict(quality.section_counts)}")
                print(f"   Coastal entities: {quality.entity_count}")

                md_s3_key = f"{BRONZE_PREFIX}{md_path.name}"
                upload_file(str(md_path), md_s3_key)

                doc_dir = bronze_tmp_path / local_pdf.stem
                if doc_dir.exists():
                    upload_directory(str(doc_dir), f"{BRONZE_PREFIX}{local_pdf.stem}/")

                print(f"   Uploaded: {md_s3_key}")
                generated.append(md_s3_key)

            except Exception as e:
                logger.error("Failed to process %s: %s", pdf_name, e)
                print(f"   Error: {e}")

    print("\n" + "=" * 60)
    print(f"Conversion complete: {len(generated)}/{len(pdf_keys)} files in s3://{BRONZE_PREFIX}")

    return generated


def process_single_pdf(
    pdf_key: str,
    output_prefix: str | None = None,
) -> tuple[str, DocumentQualityReport] | None:
    """Descarga un PDF de S3, lo procesa y sube el resultado.

    Args:
        pdf_key:       S3 key del PDF, e.g. "raw/mi_doc.pdf".
        output_prefix: Prefijo S3 de salida (por defecto BRONZE_PREFIX).

    Returns:
        (md_s3_key, quality_report) o None en caso de error.
    """
    output_prefix = output_prefix or BRONZE_PREFIX
    converter = _build_converter()

    with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as bronze_tmp:
        raw_tmp_path = Path(raw_tmp)
        bronze_tmp_path = Path(bronze_tmp)

        pdf_name = pdf_key.split("/")[-1]
        local_pdf = raw_tmp_path / pdf_name
        download_file(pdf_key, str(local_pdf))

        try:
            md_path, quality = _run_pipeline(local_pdf, bronze_tmp_path, converter)

            md_s3_key = f"{output_prefix}{md_path.name}"
            upload_file(str(md_path), md_s3_key)

            doc_dir = bronze_tmp_path / local_pdf.stem
            if doc_dir.exists():
                upload_directory(str(doc_dir), f"{output_prefix}{local_pdf.stem}/")

            return md_s3_key, quality

        except Exception as e:
            logger.error("Failed to process %s: %s", pdf_key, e)
            return None


def main() -> None:
    """CLI entry point."""
    convert_pdfs_to_markdown()


if __name__ == "__main__":
    main()
