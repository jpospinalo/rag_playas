"""Configuration for the ingest package, loaded from environment variables.

All modules in ingest/ should import their settings from here instead of
calling os.getenv() directly.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # project root
load_dotenv(BASE_DIR / ".env")

# ── S3 ─────────────────────────────────────────────────────────────────────
S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "")

# Prefijos de keys S3 (espejan la estructura local anterior data/*)
RAW_PREFIX: str = "data/raw/"
BRONZE_PREFIX: str = "data/bronze/"
SILVER_PREFIX: str = "data/silver/"
GOLD_PREFIX: str = "data/gold/"

# ── Gemini ─────────────────────────────────────────────────────────────────
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_ENRICHER_MODEL: str = os.getenv("GEMINI_ENRICHER_MODEL", GEMINI_MODEL)
