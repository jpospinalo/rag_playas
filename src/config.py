# src/config.py
"""Central configuration loaded from environment variables.

All modules should import their settings from here instead of
calling os.getenv() directly.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
CHUNKED_DIR = SILVER_DIR / "chunked"
GOLD_DIR = DATA_DIR / "gold"

# ── Chroma ─────────────────────────────────────────────────────────────────
CHROMA_HOST: str = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "poe_rag")

# ── Ollama ─────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_RERANKER_MODEL: str = os.getenv("OLLAMA_RERANKER_MODEL", "mistral")

# ── Gemini ─────────────────────────────────────────────────────────────────
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_ENRICHER_MODEL: str = os.getenv("GEMINI_ENRICHER_MODEL", "gemini-2.0-flash")

# ── Retriever ──────────────────────────────────────────────────────────────
DEFAULT_K: int = int(os.getenv("DEFAULT_K", "4"))
DEFAULT_K_CANDIDATES: int = int(os.getenv("DEFAULT_K_CANDIDATES", "10"))
