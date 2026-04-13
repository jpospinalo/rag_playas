# rag/core/vectorstore.py

from __future__ import annotations

import json
import os
from typing import Any

import chromadb
from dotenv import load_dotenv

from .embeddings import OllamaEmbeddingFunction

# ---------------------------------------------------------------------
# Constantes y configuración
# ---------------------------------------------------------------------

load_dotenv()

CHROMA_HOST = os.getenv("CHROMA_HOST")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME")

GOLD_DIR = "data/gold"

EMBED_FN = OllamaEmbeddingFunction()


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


def load_gold_documents(
    gold_dir: str = GOLD_DIR,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """
    Lee todos los .jsonl de la carpeta GOLD y devuelve:

        (ids, texts, metadatas)

    donde:
        - ids        : identificadores únicos por chunk
        - texts      : contenido textual a indexar
        - metadatas  : metadatos saneados para Chroma
    """
    ids: list[str] = []
    texts: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for file_name in os.listdir(gold_dir):
        if not file_name.endswith(".jsonl"):
            continue

        path = os.path.join(gold_dir, file_name)
        with open(path, encoding="utf-8") as f:
            for line_idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue

                rec = json.loads(line)

                text = rec.get("page_content") or rec.get("text") or rec.get("content") or ""
                if not text.strip():
                    continue

                meta: dict[str, Any] = rec.get("metadata", {}) or {}

                # ID del chunk
                chunk_id = meta.get("chunk_id") or f"{file_name}_line_{line_idx}"
                meta["chunk_id"] = chunk_id

                # Asegurar source por defecto
                meta.setdefault("source", meta.get("source", file_name))

                # Opcional: string plano de keywords
                if isinstance(meta.get("keywords"), list):
                    meta["keywords_str"] = ", ".join(meta["keywords"])

                # Sanear tipos para Chroma
                meta = sanitize_metadata(meta)

                ids.append(str(chunk_id))
                texts.append(text)
                metadatas.append(meta)

    return ids, texts, metadatas


# ---------------------------------------------------------------------
# Construir / cargar vector store en Chroma
# ---------------------------------------------------------------------


def build_or_load_vectorstore(
    gold_dir: str = GOLD_DIR,
    collection_name: str = CHROMA_COLLECTION_NAME,
):
    """
    Construye (o actualiza) una colección Chroma a partir de la capa GOLD.

    Comportamiento:
      - Conecta a Chroma vía HttpClient.
      - Crea (o recupera) la colección `collection_name`.
      - Calcula los embeddings con Ollama para los nuevos chunks.
      - Añade solo los ids que aún no existen en la colección.
    """
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collection = client.get_or_create_collection(name=collection_name)

    print(
        f"[Chroma] Colección '{collection_name}' tiene actualmente {collection.count()} documentos."
    )

    ids, texts, metadatas = load_gold_documents(gold_dir)
    if not ids:
        raise RuntimeError(f"No se encontraron documentos válidos en {gold_dir}")

    existing = collection.get(ids=ids, include=[])
    existing_ids = set(existing.get("ids", []))

    new_ids: list[str] = []
    new_texts: list[str] = []
    new_metadatas: list[dict[str, Any]] = []

    for i, t, m in zip(ids, texts, metadatas, strict=False):
        if i in existing_ids:
            continue
        new_ids.append(i)
        new_texts.append(t)
        new_metadatas.append(m)

    if not new_ids:
        print("[Chroma] Todos los chunks de GOLD ya están indexados. No se añade nada nuevo.")
        return collection

    print(
        f"[Chroma] Ingestando {len(new_ids)} documentos nuevos "
        f"en la colección '{collection_name}'..."
    )

    new_embeddings = EMBED_FN(new_texts)

    collection.add(
        ids=new_ids,
        documents=new_texts,
        metadatas=new_metadatas,
        embeddings=new_embeddings,
    )
    print("[Chroma] Ingesta completada.")

    return collection


# ---------------------------------------------------------------------
# Prueba rápida desde línea de comandos
# ---------------------------------------------------------------------


def test_query(query: str, n_results: int = 3) -> None:
    """
    Realiza una consulta simple contra la colección configurada
    y muestra los resultados en formato JSON.
    """
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collection = client.get_collection(name=CHROMA_COLLECTION_NAME)

    q_emb = EMBED_FN([query])[0]

    results = collection.query(
        query_embeddings=[q_emb],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build_or_load_vectorstore()
    print("\nEjemplo de búsqueda:")
    test_query("¿como se llamaba el gato del cuento?", n_results=1)
