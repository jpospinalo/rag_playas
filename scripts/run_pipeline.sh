#!/usr/bin/env bash
set -euo pipefail

echo "=== 1/5 Conversión PDF → Markdown ==="
uv run python -m ingest.pdf_to_md

echo "=== 2/5 Ingesta y normalización ==="
uv run python -m ingest.loaders

echo "=== 3/5 Chunking + Enriquecimiento con Gemini ==="
uv run python -m ingest.splitter_and_enrich

echo "=== 4/5 Indexación en ChromaDB ==="
uv run python -m rag.core.vectorstore

echo "=== 5/5 Lanzando API FastAPI ==="
uv run uvicorn rag.api.main:app --reload --port 8080
