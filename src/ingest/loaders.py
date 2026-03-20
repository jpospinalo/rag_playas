# src/ingest/loaders.py

from __future__ import annotations

from pathlib import Path
from typing import List

from dotenv import load_dotenv
from langchain_core.documents import Document

from .normalize import normalize_documents
from .utils import save_docs_jsonl_per_file

load_dotenv()

# Rutas base
DATA_DIR = Path("data")
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"


# ---------------------------------------------------------------------
# Funciones principales
# ---------------------------------------------------------------------

def load_documents() -> List[Document]:
    """
    Carga Markdowns de data/bronze/ y genera la capa SILVER (JSONL).

    Flujo:
      1) Lee cada archivo .md de BRONZE_DIR.
      2) Normaliza texto y metadatos.
      3) Guarda un .jsonl por archivo en SILVER_DIR.

    Devuelve:
        Lista de Document de LangChain.
    """
    md_files = sorted(BRONZE_DIR.glob("*.md"))
    if not md_files:
        print(f"No se encontraron archivos .md en {BRONZE_DIR}")
        return []

    raw_docs: List[Document] = []
    for md_path in md_files:
        content = md_path.read_text(encoding="utf-8")
        doc = Document(
            page_content=content,
            metadata={"source": md_path.name},
        )
        raw_docs.append(doc)

    print(f"Documentos cargados desde Markdown: {len(raw_docs)}")

    docs = normalize_documents(raw_docs)
    print(f"Documentos normalizados: {len(docs)}")

    save_docs_jsonl_per_file(docs, SILVER_DIR)
    print(f"Documentos guardados en: {SILVER_DIR}")

    return docs


def main() -> None:
    documents = load_documents()
    if not documents:
        print("No hay documentos.")
        return

    print(f"Total documentos: {len(documents)}")

    ejemplo_idx = 1 if len(documents) > 1 else 0
    print("Ejemplo metadata:", documents[ejemplo_idx].metadata)
    print("Ejemplo texto (primeros 500 chars):\n", documents[ejemplo_idx].page_content[:500])


if __name__ == "__main__":
    main()
