# ingest/loaders.py

from __future__ import annotations

from langchain_core.documents import Document

from .config import BRONZE_PREFIX, SILVER_PREFIX
from .metadata_csv import get_metadata_for_file, load_metadata_csv
from .normalize import normalize_documents
from .s3_client import list_keys, read_text
from .sections import split_by_sections
from .utils import save_docs_jsonl_per_file


def load_documents() -> list[Document]:
    """
    Carga Markdowns de S3 bronze/ y genera la capa SILVER (JSONL en S3).

    Flujo:
      1) Lee cada archivo .md de bronze/ en S3.
      2) Normaliza texto y metadatos.
      3) Guarda un .jsonl por archivo en silver/ en S3.

    Devuelve:
        Lista de Document de LangChain.
    """
    md_keys = sorted(list_keys(BRONZE_PREFIX, suffix=".md"))
    if not md_keys:
        print(f"No se encontraron archivos .md en s3://{BRONZE_PREFIX}")
        return []

    raw_docs: list[Document] = []
    for key in md_keys:
        content = read_text(key)
        filename = key.split("/")[-1]
        doc = Document(
            page_content=content,
            metadata={"source": filename},
        )
        raw_docs.append(doc)

    print(f"Documentos cargados desde Markdown: {len(raw_docs)}")

    docs = normalize_documents(raw_docs)
    print(f"Documentos normalizados: {len(docs)}")

    matched_count = 0
    csv_rows = len(load_metadata_csv())
    for doc in docs:
        csv_meta = get_metadata_for_file(doc.metadata.get("source", ""))
        if csv_meta:
            doc.metadata.update(csv_meta)
            matched_count += 1
            print(f"  → Metadatos CSV encontrados para: {doc.metadata.get('source', '?')}")

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
            print(
                f"    {marker} Sección {m['section_index']} – {m['section_name']:<30} {heading!r:<45} {status}"
            )
        sectioned_docs.extend(sections)

    detected = sum(1 for d in sectioned_docs if d.page_content)
    print(
        f"\nSecciones detectadas: {detected}/{len(sectioned_docs)} con contenido ({len(docs)} documentos)"
    )

    save_docs_jsonl_per_file(sectioned_docs, SILVER_PREFIX)
    print(f"Guardado en: s3://{SILVER_PREFIX}")

    print(
        f"\nMetadatos CSV: {matched_count}/{csv_rows} filas con archivo ({len(docs)} documentos processados)\n"
    )

    return sectioned_docs


def main() -> None:
    documents = load_documents()
    if not documents:
        print("No hay documentos.")
        return

    print(f"Total secciones: {len(documents)}")


if __name__ == "__main__":
    main()
