"""
Main PDF-to-Markdown conversion pipeline.

Orchestrates Docling OCR, document profiling, adaptive cleanup, semantic
segmentation, entity extraction, quality evaluation, and file output.
"""

from __future__ import annotations

import json
import logging
import time
import warnings
from dataclasses import asdict
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import ImageRefMode

logging.getLogger("docling").setLevel(logging.WARNING)
logging.getLogger("rapidocr").setLevel(logging.WARNING)
logging.getLogger("onnxruntime").setLevel(logging.WARNING)

from .cleaner import adaptive_cleanup
from .config import BRONZE_DIR, IMAGE_RESOLUTION_SCALE, RAW_DIR
from .images import relativize_image_refs
from .models import DocumentQualityReport
from .profiler import profile_legal_document
from .quality import evaluate_document_quality
from .segmenter import extract_coastal_legal_entities, segment_legal_sections

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
    """Run the full processing pipeline for a single PDF.

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


def convert_pdfs_to_markdown() -> list[Path]:
    """Convert all PDFs from ``data/raw/`` to cleaned Markdown in ``data/bronze/``.

    Full pipeline per PDF:
    1. Docling OCR conversion
    2. Markdown extraction
    3. Legal document profiling
    4. Adaptive cleanup
    5. Semantic section segmentation
    6. Coastal entity extraction
    7. Quality evaluation
    8. Write final ``.md`` + JSON sidecars

    Returns list of generated ``.md`` files.
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

        try:
            md_path, quality = _run_pipeline(pdf_path, BRONZE_DIR, converter)

            print(f"   ⏱️  Time: {quality.processing_time_seconds:.1f}s")
            print(f"   📊 Quality: {quality.final_quality:.1f}%")
            print(f"   📑 Sections: {dict(quality.section_counts)}")
            print(f"   🏖️  Coastal entities: {quality.entity_count}")
            print(f"   ✅ Output: {md_path.name}")

            generated.append(md_path)

        except Exception as e:
            logger.error("Failed to process %s: %s", pdf_path.name, e)
            print(f"   ❌ Error: {e}")

    print("\n" + "=" * 60)
    print(f"Conversion complete: {len(generated)}/{len(pdf_paths)} files in {BRONZE_DIR}")

    return generated


def process_single_pdf(
    pdf_path: Path,
    output_dir: Path | None = None,
) -> tuple[Path, DocumentQualityReport] | None:
    """Process a single PDF through the full pipeline.

    Args:
        pdf_path:   Path to the input PDF.
        output_dir: Output directory (defaults to ``BRONZE_DIR``).

    Returns:
        ``(output_md_path, quality_report)`` or ``None`` on failure.
    """
    output_dir = output_dir or BRONZE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    converter = _build_converter()

    try:
        return _run_pipeline(pdf_path, output_dir, converter)
    except Exception as e:
        logger.error("Failed to process %s: %s", pdf_path, e)
        return None


def main() -> None:
    """CLI entry point."""
    convert_pdfs_to_markdown()


if __name__ == "__main__":
    main()
