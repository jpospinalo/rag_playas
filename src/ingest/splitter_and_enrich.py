# src/ingest/splitter_and_enrich.py
# Paso unificado: data/silver/ -> data/gold/
# Combina el chunking (splitter) y el enriquecimiento con Gemini (enrich)
# en un único módulo, eliminando la capa intermedia data/silver/chunked/.

from __future__ import annotations

from pathlib import Path

from .enrich import GeminiEnricher, write_jsonl
from .splitter import chunk_documents
from .utils import load_all_docs_from_dir

# ---------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------

DATA_DIR = Path("data")
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"


# ---------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------


def split_and_enrich_directory(
    silver_dir: Path = SILVER_DIR,
    gold_dir: Path = GOLD_DIR,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    max_calls_per_minute: int = 9,
) -> None:
    """
    Lee los documentos de *silver_dir*, los fragmenta y los enriquece con
    Gemini, escribiendo el resultado directamente en *gold_dir*.

    Flujo interno:
        1. Cargar documentos desde data/silver/*.jsonl
        2. Fragmentar con RecursiveCharacterTextSplitter (via chunk_documents)
        3. Enriquecer cada chunk con GeminiEnricher (summary, keywords, entities)
        4. Escribir los chunks enriquecidos en data/gold/*.jsonl
    """
    # TODO: implementar
    pass


def main() -> None:
    split_and_enrich_directory()


if __name__ == "__main__":
    main()
