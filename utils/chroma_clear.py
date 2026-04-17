"""Script para eliminar todos los documentos de la colección activa en Chroma."""

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
    print(f"Colección: '{CHROMA_COLLECTION}'")
    print(f"Documentos actuales: {count}")

    if count == 0:
        print("La colección ya está vacía. No hay nada que eliminar.")
        return

    respuesta = input("\n¿Eliminar todos los documentos? [y/N] ").strip().lower()
    if respuesta != "y":
        print("Operación cancelada.")
        return

    client.delete_collection(CHROMA_COLLECTION)
    client.create_collection(CHROMA_COLLECTION)
    print(f"Colección '{CHROMA_COLLECTION}' vaciada. Documentos eliminados: {count}")


if __name__ == "__main__":
    main()
