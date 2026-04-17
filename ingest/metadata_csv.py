# ingest/metadata_csv.py

from __future__ import annotations

import csv
import io

from .config import RAW_PREFIX
from .s3_client import read_text

_csv_cache: dict[str, dict] | None = None


def load_metadata_csv() -> dict[str, dict]:
    global _csv_cache
    if _csv_cache is not None:
        return _csv_cache

    _csv_cache = {}
    content = read_text(f"{RAW_PREFIX}metadata.csv")
    reader = csv.DictReader(io.StringIO(content), delimiter=";")
    for row in reader:
        archivo = row.get("Archivo", "").strip()
        if archivo:
            _csv_cache[archivo] = {k: v.strip() for k, v in row.items() if v.strip()}
    return _csv_cache


def get_metadata_for_file(filename: str) -> dict | None:
    # Normalizar extensión .md → .pdf para hacer match con la columna Archivo del CSV
    lookup = filename
    if lookup.endswith(".md"):
        lookup = lookup[:-3] + ".pdf"
    return load_metadata_csv().get(lookup)
