# src/backend/embeddings.py

import os
from typing import cast

import requests
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from langchain_core.embeddings import Embeddings as LCEmbeddings


class OllamaEmbeddingClient:
    """Shared HTTP client for Ollama embeddings."""

    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL") or os.getenv(
            "OLLAMA_EMBED_BASE_URL", "http://localhost:11434"
        )
        self.model = os.getenv("OLLAMA_EMBEDDING_MODEL") or os.getenv(
            "OLLAMA_EMBED_MODEL", "nomic-embed-text"
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": texts[0]},
                timeout=30,
            )
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                "No fue posible conectar con Ollama para calcular embeddings. "
                f"Verifica que el servicio esté activo en {self.base_url} "
                f"y que el modelo '{self.model}' esté disponible."
            ) from exc
        response.raise_for_status()
        return [response.json()["embedding"]]


class OllamaEmbeddingFunction(EmbeddingFunction):
    """ChromaDB-compatible embedding function backed by Ollama."""

    def __init__(self) -> None:
        self._client = OllamaEmbeddingClient()

    def __call__(self, input: Documents) -> Embeddings:
        return cast(Embeddings, [self._client.embed([text])[0] for text in input])


class OllamaEmbeddings(LCEmbeddings):
    """LangChain-compatible embeddings backed by Ollama."""

    def __init__(self) -> None:
        self._client = OllamaEmbeddingClient()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._client.embed([t])[0] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed([text])[0]
