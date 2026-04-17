import json
from collections import defaultdict
from pathlib import Path

from langchain_core.documents import Document

from .s3_client import key_exists, list_keys, read_text, write_text


def _save_docs_jsonl_file(docs: list[Document], key: str) -> None:
    """Sube una lista de Documents como un único objeto .jsonl a S3."""
    lines = [
        json.dumps({"page_content": d.page_content, "metadata": d.metadata}, ensure_ascii=False)
        for d in docs
    ]
    write_text(key, "\n".join(lines) + "\n")


def save_docs_jsonl_per_file(docs: list[Document], prefix: str) -> None:
    """Sube un .jsonl por archivo original (agrupando por metadata['source']).

    prefix: e.g. "silver/"  (con slash al final)
    """
    grouped: dict[str, list[Document]] = defaultdict(list)
    for d in docs:
        source = d.metadata.get("source", "document")
        stem = Path(source).stem
        grouped[stem].append(d)

    for stem, group_docs in grouped.items():
        _save_docs_jsonl_file(group_docs, f"{prefix}{stem}.jsonl")


def _load_docs_jsonl_file(key: str) -> list[Document]:
    """Descarga un objeto .jsonl de S3 y devuelve una lista de Documents."""
    content = read_text(key)
    docs: list[Document] = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        docs.append(
            Document(
                page_content=row["page_content"],
                metadata=row.get("metadata", {}),
            )
        )
    return docs


def load_all_docs_from_dir(prefix: str) -> list[Document]:
    """Carga todos los .jsonl bajo un prefijo S3."""
    docs: list[Document] = []
    for key in list_keys(prefix, suffix=".jsonl"):
        docs.extend(_load_docs_jsonl_file(key))
    return docs


def load_docs_by_source(prefix: str, source_name: str) -> list[Document]:
    """Carga solo los documentos de un archivo concreto desde S3.

    source_name puede ser "mi_doc.pdf" o "mi_doc".
    """
    stem = Path(source_name).stem
    key = f"{prefix}{stem}.jsonl"
    if not key_exists(key):
        print(f"No se encontró el objeto S3: {key}")
        return []
    return _load_docs_jsonl_file(key)
