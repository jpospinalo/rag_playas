# src/ingest/loaders.py

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document

from .normalize import normalize_documents
from .sections import split_by_sections
from .utils import save_docs_jsonl_per_file

load_dotenv()

# Rutas base
DATA_DIR = Path("data")
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"


# ---------------------------------------------------------------------
# Funciones principales
# ---------------------------------------------------------------------


def load_documents() -> list[Document]:
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

    raw_docs: list[Document] = []
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

    sectioned_docs: list[Document] = []
    for doc in docs:
        sections = split_by_sections(doc)
        title = doc.metadata.get("title") or doc.metadata.get("source", "?")
        print(f"\n  [{title}]")
        for s in sections:
            m = s.metadata
            heading = m.get("section_heading") or "(sin heading)"
            found = bool(s.page_content)
            status = f"{len(s.page_content):>6} chars" if found else "  vacío      "
            marker = "✓" if found else "✗"
            print(f"    {marker} Sección {m['section_index']} – {m['section_name']:<30} {heading!r:<45} {status}")
        sectioned_docs.extend(sections)

    detected = sum(1 for d in sectioned_docs if d.page_content)
    print(f"\nSecciones detectadas: {detected}/{len(sectioned_docs)} con contenido ({len(docs)} documentos)")

    save_docs_jsonl_per_file(sectioned_docs, SILVER_DIR)
    print(f"Guardado en: {SILVER_DIR}\n")

    return sectioned_docs


def main() -> None:
    documents = load_documents()
    if not documents:
        print("No hay documentos.")
        return

    print(f"Total secciones: {len(documents)}")


if __name__ == "__main__":
    main()
