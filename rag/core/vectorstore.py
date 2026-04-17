# rag/core/vectorstore.py

from __future__ import annotations

import json
import os
import time
from typing import Any

import chromadb
from dotenv import load_dotenv

from ..config import GOLD_PREFIX
from ..s3_client import list_keys, read_text
from .embeddings import OllamaEmbeddingFunction

# ---------------------------------------------------------------------
# Constantes y configuración
# ---------------------------------------------------------------------

load_dotenv()

CHROMA_HOST = os.getenv("CHROMA_HOST")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME")

EMBED_FN = OllamaEmbeddingFunction()

# Tamaño máximo de cada batch para embeddings e ingesta en Chroma
BATCH_SIZE = 500

# Retry para errores de red
MAX_RETRIES = 3
INITIAL_BACKOFF = 2.0  # segundos


# ---------------------------------------------------------------------
# Utilidad: sanear metadatos
# ---------------------------------------------------------------------


def sanitize_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """
    Adapta metadatos a los tipos permitidos por Chroma 1.x.

    Chroma solo acepta valores: str, int, float, bool o None.
    Cualquier lista o dict se convierte en un JSON string.
    """
    safe: dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            safe[k] = v
        else:
            safe[k] = json.dumps(v, ensure_ascii=False)
    return safe


# ---------------------------------------------------------------------
# Carga de documentos GOLD
# ---------------------------------------------------------------------


def _build_embedding_text(text: str, meta: dict[str, Any]) -> str:
    """
    Construye el texto aumentado para embedding combinando metadatos clave
    con el contenido del chunk (Contextual Chunk Headers).

    El vector resultante captura tanto el contenido semántico como el
    contexto documental (sección, tema, keywords, resumen). El texto
    original se almacena por separado en ChromaDB para que el LLM lo reciba limpio.
    """
    parts: list[str] = []
    if kw := meta.get("keywords_str", ""):
        parts.append(f"Palabras clave: {kw}")
    if summary := meta.get("summary", ""):
        parts.append(f"Resumen: {summary}")
    if parts:
        return "\n".join(parts) + "\n\n" + text
    return text


def load_gold_records(
    key: str,
) -> tuple[list[str], list[str], list[str], list[dict[str, Any]]]:
    """
    Descarga un objeto .jsonl de S3 (capa GOLD) y devuelve
    (ids, texts, embed_texts, metadatas).

    - ``texts``       — page_content original; se almacena en Chroma como documento.
    - ``embed_texts`` — texto aumentado con encabezados de metadatos; se usa solo
                        para generar los embeddings (Contextual Chunk Headers).
    """
    ids: list[str] = []
    texts: list[str] = []
    embed_texts: list[str] = []
    metadatas: list[dict[str, Any]] = []

    file_name = key.split("/")[-1]
    content = read_text(key)
    for line_idx, line in enumerate(content.splitlines()):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        text = rec.get("page_content") or rec.get("text") or rec.get("content") or ""
        if not text.strip():
            continue
        meta: dict[str, Any] = rec.get("metadata", {}) or {}
        chunk_id = meta.get("chunk_id") or f"{file_name}_line_{line_idx}"
        meta["chunk_id"] = chunk_id
        meta.setdefault("source", meta.get("source", file_name))
        if isinstance(meta.get("keywords"), list):
            meta["keywords_str"] = ", ".join(meta["keywords"])
        meta = sanitize_metadata(meta)
        ids.append(str(chunk_id))
        texts.append(text)
        embed_texts.append(_build_embedding_text(text, meta))
        metadatas.append(meta)

    return ids, texts, embed_texts, metadatas


# ---------------------------------------------------------------------
# Construir / cargar vector store en Chroma
# ---------------------------------------------------------------------


def build_or_load_vectorstore(
    gold_prefix: str = GOLD_PREFIX,
    collection_name: str = CHROMA_COLLECTION_NAME,
):
    """
    Construye (o actualiza) una colección Chroma a partir de la capa GOLD en S3.

    Comportamiento:
      - Conecta a Chroma vía HttpClient.
      - Crea (o recupera) la colección `collection_name`.
      - Procesa archivos en orden lexicográfico (determinístico).
      - Carga solo los ids que aún no existen en la colección.
      - Procesa en batches de máximo BATCH_SIZE chunks por archivo.
      - Retry con exponential backoff (3 intentos) ante errores de red.
      - Aborta toda la operación si un batch falla tras los 3 intentos.
    """
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collection = client.get_or_create_collection(name=collection_name)

    count_before = collection.count()
    gold_keys = list_keys(gold_prefix, suffix=".jsonl")
    total_files = len(gold_keys)

    if not gold_keys:
        raise RuntimeError(f"No se encontraron archivos .jsonl en s3://{gold_prefix}")

    print(f"[Chroma] Colección: {count_before} docs → ingestando {total_files} archivos...")

    total_new = 0
    files_indexed = 0
    files_skipped = 0

    for file_idx, key in enumerate(gold_keys, start=1):
        file_name = key.split("/")[-1]
        ids, texts, embed_texts, metadatas = load_gold_records(key)

        if not ids:
            print(f"[{file_idx}/{total_files}] {file_name} → vacío → skipped")
            files_skipped += 1
            continue

        existing = collection.get(ids=ids, include=[])
        existing_ids = set(existing.get("ids", []))
        new_ids_set = set(ids) - existing_ids

        if not new_ids_set:
            print(
                f"[{file_idx}/{total_files}] {file_name} | {len(ids)} chunks | 0 nuevos (ya indexados)"
            )
            files_skipped += 1
            continue

        new_ids: list[str] = []
        new_texts: list[str] = []
        new_embed_texts: list[str] = []
        new_metadatas: list[dict[str, Any]] = []
        for i, t, et, m in zip(ids, texts, embed_texts, metadatas, strict=False):
            if i in new_ids_set:
                new_ids.append(i)
                new_texts.append(t)
                new_embed_texts.append(et)
                new_metadatas.append(m)

        print(f"[{file_idx}/{total_files}] {file_name} | {len(ids)} chunks | {len(new_ids)} nuevos")

        num_batches = (len(new_ids) + BATCH_SIZE - 1) // BATCH_SIZE

        for batch_idx in range(num_batches):
            start = batch_idx * BATCH_SIZE
            end = start + BATCH_SIZE
            batch_ids = new_ids[start:end]
            batch_texts = new_texts[start:end]
            batch_embed_texts = new_embed_texts[start:end]
            batch_metas = new_metadatas[start:end]

            if num_batches > 1:
                print(f"       Batch {batch_idx + 1}/{num_batches}: {len(batch_ids)} chunks...")

            for attempt in range(MAX_RETRIES):
                try:
                    # Los embeddings se generan desde el texto aumentado (contextual chunk
                    # headers), pero se almacena el page_content original como documento.
                    embeddings = EMBED_FN(batch_embed_texts)
                    collection.add(
                        ids=batch_ids,
                        documents=batch_texts,
                        metadatas=batch_metas,
                        embeddings=embeddings,
                    )
                except Exception as exc:
                    if attempt < MAX_RETRIES - 1:
                        backoff = INITIAL_BACKOFF * (2**attempt)
                        print(
                            f"       Batch {batch_idx + 1} error "
                            f"(intento {attempt + 1}/{MAX_RETRIES}): {exc}. "
                            f"Reintentando en {backoff:.1f}s..."
                        )
                        time.sleep(backoff)
                    else:
                        exc_str = str(exc).lower()
                        if any(
                            k in exc_str
                            for k in [
                                "connect",
                                "connection",
                                "refused",
                                "timeout",
                                "reset",
                                "socket",
                                "httpexception",
                            ]
                        ):
                            service = "ChromaDB (conexión)"
                        elif any(k in exc_str for k in ["ollama", "embed", "embedding", "model"]):
                            service = "Ollama (embeddings)"
                        else:
                            service = f"desconocido: {type(exc).__name__}"

                        raise RuntimeError(
                            f"ERROR en batch {batch_idx + 1}/{num_batches} de "
                            f"[{file_idx}/{total_files}] {file_name} → {service}. "
                            f"Chunks: {batch_ids[:5]}"
                        ) from exc

            if num_batches == 1:
                print(f"       {len(batch_ids)} chunks → OK")

        total_new += len(new_ids)
        files_indexed += 1

    count_after = collection.count()
    print(
        f"[Chroma] {count_before} → {count_after} docs "
        f"(+{total_new} nuevos, {files_indexed} indexados, {files_skipped} skipped)"
    )

    return collection


if __name__ == "__main__":
    build_or_load_vectorstore()
