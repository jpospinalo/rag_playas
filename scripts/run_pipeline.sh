#!/usr/bin/env bash
set -euo pipefail

echo "=== 1/5 Conversión PDF → Markdown ==="
uv run python -m src.ingest.pdf_to_md

echo "=== 2/5 Ingesta y normalización ==="
uv run python -m src.ingest.loaders

echo "=== 3/5 Chunking + Enriquecimiento con Gemini ==="
uv run python -m src.ingest.splitter_and_enrich

echo "=== 4/5 Indexación en ChromaDB ==="
uv run python -m src.backend.vectorstore

echo "=== 5/5 Lanzando interfaz Gradio ==="
uv run python -m src.frontend.gradio_app
