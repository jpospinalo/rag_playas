# src/utils.py

import json
from collections import defaultdict
from pathlib import Path

from langchain_core.documents import Document


def _save_docs_jsonl_file(docs: list[Document], path: Path) -> None:
    """Guarda una lista de Documents en un único archivo .jsonl."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for d in docs:
            row = {
                "page_content": d.page_content,
                "metadata": d.metadata,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def save_docs_jsonl_per_file(docs: list[Document], dir_path: Path) -> None:
    """
    Guarda un .jsonl por archivo original (agrupando por metadata['source']).

    Ejemplo de salida en dir_path:
      El_cuervo-Allan_Poe_Edgar.jsonl
      El_corazon_delator-Allan_Poe_Edgar.jsonl
    """
    dir_path.mkdir(parents=True, exist_ok=True)

    grouped = defaultdict(list)
    for d in docs:
        source = d.metadata.get("source", "document")
        stem = Path(source).stem
        grouped[stem].append(d)

    for stem, group_docs in grouped.items():
        out_path = dir_path / f"{stem}.jsonl"
        _save_docs_jsonl_file(group_docs, out_path)


def _load_docs_jsonl_file(path: Path) -> list[Document]:
    """Carga un archivo .jsonl y devuelve una lista de Documents."""
    docs: list[Document] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            docs.append(
                Document(
                    page_content=row["page_content"],
                    metadata=row.get("metadata", {}),
                )
            )
    return docs


def load_all_docs_from_dir(dir_path: Path) -> list[Document]:
    """Carga todos los .jsonl de un directorio."""
    docs: list[Document] = []
    for jsonl_path in sorted(dir_path.glob("*.jsonl")):
        docs.extend(_load_docs_jsonl_file(jsonl_path))
    return docs


def load_docs_by_source(dir_path: Path, source_name: str) -> list[Document]:
    """
    Carga solo los documentos de un archivo concreto.

    source_name puede ser:
      - "El_cuervo-Allan_Poe_Edgar"
      - "El_cuervo-Allan_Poe_Edgar.pdf"
    """
    stem = Path(source_name).stem
    jsonl_path = dir_path / f"{stem}.jsonl"

    if not jsonl_path.exists():
        print(f"No se encontró el archivo: {jsonl_path}")
        return []

    return _load_docs_jsonl_file(jsonl_path)
