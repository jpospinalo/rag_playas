"""Script para consultar la cantidad de documentos en la colección de Chroma."""

import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv

# ── Configuración ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION_NAME", "rag_playas_docs")


def main() -> None:
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collection = client.get_or_create_collection(name=CHROMA_COLLECTION)
    count = collection.count()
    print(f"Cantidad de documentos en '{CHROMA_COLLECTION}': {count}")


if __name__ == "__main__":
    main()
