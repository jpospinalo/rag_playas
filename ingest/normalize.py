# src/ingest/normalize.py

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from langchain_core.documents import Document


def normalize_text(text: str) -> str:
    """
    Limpieza del texto preservando la estructura Markdown.

    - Elimina espacios en blanco al final de cada línea.
    - Colapsa 3+ líneas en blanco consecutivas a máximo 2.
    - Elimina caracteres de control no imprimibles (excepto saltos de línea y tabs).
    """
    text = re.sub(r"[^\S\n\t]", " ", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """
    Normaliza la metadata partiendo del campo 'source'.

    Conserva el nombre del archivo en 'source' y genera un 'title'
    legible a partir del stem del archivo (reemplaza guiones bajos
    por espacios).
    """
    src = meta.get("source", "")
    file_path = Path(src)
    filename = file_path.name
    stem = file_path.stem

    title = stem.replace("_", " ").strip()

    return {
        "source": filename,
        "title": title or None,
    }


def normalize_documents(docs: list[Document]) -> list[Document]:
    """
    Aplica normalize_text y normalize_metadata a una lista de Documents.

    Devuelve:
        Lista de Document normalizados (nuevo objeto por cada entrada).
    """
    normalized: list[Document] = []

    for d in docs:
        text = normalize_text(d.page_content)
        meta = normalize_metadata(d.metadata)
        normalized.append(Document(page_content=text, metadata=meta))

    return normalized
