#!/usr/bin/env bash
set -euo pipefail

echo "=== 1/6 Conversión PDF → Markdown ==="
uv run python -m src.ingest.pdf_to_md

echo "=== 2/6 Ingesta y normalización ==="
uv run python -m src.ingest.loaders

echo "=== 3/6 Chunking ==="
uv run python -m src.ingest.splitter

echo "=== 4/6 Enriquecimiento con Gemini ==="
uv run python -m src.ingest.enrich

echo "=== 5/6 Indexación en ChromaDB ==="
uv run python -m src.backend.vectorstore

echo "=== 6/6 Lanzando interfaz Gradio ==="
uv run python -m src.frontend.gradio_app
