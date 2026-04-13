"""Pipeline unificado Silver → Gold.

Lee los documentos seccionales de data/silver/, los fragmenta con tamaño
óptimo para embeddings y los enriquece con metadatos generados por Gemini,
escribiendo el resultado directamente en data/gold/ sin pasar por ninguna
capa intermedia.
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from google import genai
from google.genai import types as genai_types
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field

from .config import GEMINI_ENRICHER_MODEL, GOLD_DIR, SILVER_DIR
from .utils import _load_docs_jsonl_file, save_docs_jsonl_per_file

logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200

# ---------------------------------------------------------------------------
# Pydantic output schema for Gemini
# ---------------------------------------------------------------------------


class Entity(BaseModel):
    type: str = Field(
        description="Tipo de entidad: PERSON, LOCATION, DATE u otro valor descriptivo."
    )
    text: str = Field(description="Texto exacto de la entidad en el chunk.")


class ChunkMetadata(BaseModel):
    summary: str = Field(
        description="Resumen muy breve del contenido del chunk (máx. ~40 palabras)."
    )
    keywords: list[str] = Field(
        description="Lista de 5 a 10 palabras o frases clave relevantes para búsqueda."
    )
    entities: list[Entity] = Field(
        description="Lista de entidades nombradas (personas, lugares, fechas, etc.)."
    )


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


@dataclass
class RateLimiter:
    max_calls: int
    period_seconds: int = 60

    def __post_init__(self) -> None:
        self._calls: deque[float] = deque()

    def wait_for_slot(self) -> None:
        now = time.time()
        while self._calls and now - self._calls[0] > self.period_seconds:
            self._calls.popleft()

        if len(self._calls) >= self.max_calls:
            wait = self.period_seconds - (now - self._calls[0]) + 0.1
            logger.info("RateLimiter: esperando %.1fs para respetar el límite...", wait)
            time.sleep(wait)
            now = time.time()
            while self._calls and now - self._calls[0] > self.period_seconds:
                self._calls.popleft()

        self._calls.append(time.time())


# ---------------------------------------------------------------------------
# Gemini enricher
# ---------------------------------------------------------------------------


class GeminiEnricher:
    """Genera summary, keywords y entities para un chunk usando Gemini."""

    def __init__(
        self,
        model: str = GEMINI_ENRICHER_MODEL,
        max_calls_per_minute: int = 9,
    ) -> None:
        if not GOOGLE_API_KEY:
            raise RuntimeError(
                "GOOGLE_API_KEY no está definida. Asegúrate de declararla en el archivo .env."
            )
        self.client = genai.Client(api_key=GOOGLE_API_KEY)
        self.model = model
        self.rate_limiter = RateLimiter(max_calls=max_calls_per_minute)

    def enrich_chunk(
        self,
        text: str,
        doc_metadata: dict | None = None,
    ) -> ChunkMetadata:
        """Enriquece un chunk de texto. Soporta Gemini 2.x (JSON mode) y Gemma-3 (prompting)."""
        import json

        self.rate_limiter.wait_for_slot()
        print(f"  [model] enriqueciendo datos con modelo: {self.model}")

        meta_str = ""
        if doc_metadata:
            meta_str = (
                "Metadatos del documento (pueden ayudar a contextualizar el fragmento):\n"
                f"{json.dumps(doc_metadata, ensure_ascii=False)}\n\n"
            )

        base_prompt = (
            "Eres un asistente para preparar datos de un sistema de Recuperación "
            "Aumentada por Generación (RAG) en español. A partir del siguiente "
            "fragmento de texto (chunk), debes generar:\n"
            "1) Un resumen muy breve (máximo ~40 palabras) que capture la idea "
            "   principal del chunk.\n"
            "2) Entre 5 y 10 palabras clave relevantes para búsqueda semántica.\n"
            "3) Una lista de entidades nombradas importantes (personas, lugares, "
            "   fechas, organizaciones u otras).\n\n"
            f"{meta_str}"
            "Texto del chunk:\n"
            f"{text}\n\n"
        )

        if not (self.model or "").startswith("gemma-3"):
            prompt = base_prompt + (
                "Responde SOLO con los campos solicitados en formato JSON con esta forma:\n"
                "{\n"
                '  "summary": "...",\n'
                '  "keywords": ["..."],\n'
                '  "entities": [\n'
                '    {"type": "...", "text": "..."}\n'
                "  ]\n"
                "}\n"
            )
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ChunkMetadata,
                    temperature=0.2,
                ),
            )
            return response.parsed

        # Gemma-3: sin JSON mode, parseo manual
        prompt = base_prompt + (
            "Responde SOLO con un JSON válido (sin texto adicional) con esta forma exacta:\n"
            "{\n"
            '  "summary": "texto del resumen",\n'
            '  "keywords": ["palabra1", "palabra2"],\n'
            '  "entities": [\n'
            '    {"type": "PERSON", "text": "Ejemplo de nombre"}\n'
            "  ]\n"
            "}\n"
            "No incluyas comentarios, explicaciones ni texto fuera del JSON.\n"
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(temperature=0.2),
        )

        raw = (response.text or "").strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines).strip()

        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and start < end:
            raw = raw[start : end + 1]

        data = json.loads(raw)
        return ChunkMetadata(**data)


# ---------------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------------


def _build_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
    )


def _chunk_section(doc: Document, splitter: RecursiveCharacterTextSplitter) -> list[Document]:
    """Divide un Document seccional en chunks preservando y extendiendo sus metadatos."""
    base_meta = dict(doc.metadata)
    source = base_meta.get("source", "unknown")
    stem = Path(source).stem
    section_idx = base_meta.get("section_index", 0)

    raw_chunks = splitter.split_documents([doc])
    total = len(raw_chunks)

    result: list[Document] = []
    for idx, chunk in enumerate(raw_chunks):
        meta = {
            **base_meta,
            "chunk_index": idx,
            "chunk_id": f"{stem}_s{section_idx}_c{idx}",
            "total_chunks_in_section": total,
        }
        result.append(Document(page_content=chunk.page_content, metadata=meta))

    return result


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def split_and_enrich_directory(
    silver_dir: Path = SILVER_DIR,
    gold_dir: Path = GOLD_DIR,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    model_name: str = GEMINI_ENRICHER_MODEL,
    max_calls_per_minute: int = 9,
    skip_existing: bool = True,
) -> None:
    """Lee documentos de *silver_dir*, los fragmenta y enriquece con Gemini,
    escribiendo el resultado directamente en *gold_dir*.

    Flujo por archivo:
        1. Cargar secciones desde data/silver/<file>.jsonl
        2. Fragmentar cada sección no vacía con RecursiveCharacterTextSplitter
        3. Enriquecer cada chunk con Gemini (summary, keywords, entities)
        4. Escribir chunks enriquecidos en data/gold/<file>.jsonl

    Los archivos ya presentes en gold_dir se saltan cuando skip_existing=True.
    Los errores de enriquecimiento por chunk se loggean sin interrumpir el proceso.
    """
    gold_dir.mkdir(parents=True, exist_ok=True)

    silver_files = sorted(silver_dir.glob("*.jsonl"))
    if not silver_files:
        logger.warning("No se encontraron archivos .jsonl en %s", silver_dir)
        return

    enricher = GeminiEnricher(model=model_name, max_calls_per_minute=max_calls_per_minute)
    splitter = _build_splitter(chunk_size, chunk_overlap)

    for silver_file in silver_files:
        gold_file = gold_dir / silver_file.name

        if skip_existing and gold_file.exists():
            logger.info("Saltando %s (ya existe en gold)", silver_file.name)
            print(f"[skip] {silver_file.name} ya existe en gold, se omite.")
            continue

        print(f"\n[proc] {silver_file.name}")
        section_docs = _load_docs_jsonl_file(silver_file)

        all_chunks: list[Document] = []
        for doc in section_docs:
            if not doc.page_content.strip():
                continue
            chunks = _chunk_section(doc, splitter)
            all_chunks.extend(chunks)

        print(f"  {len(section_docs)} secciones -> {len(all_chunks)} chunks")

        enriched: list[Document] = []
        for i, chunk in enumerate(all_chunks):
            logger.debug(
                "Enriqueciendo chunk %d/%d de %s", i + 1, len(all_chunks), silver_file.name
            )
            print(
                f"  [{i + 1:>3}/{len(all_chunks)}] enriqueciendo chunk_id={chunk.metadata.get('chunk_id')}"
            )

            try:
                ai = enricher.enrich_chunk(
                    text=chunk.page_content,
                    doc_metadata={
                        k: v
                        for k, v in chunk.metadata.items()
                        if k in ("source", "title", "section_name", "section_heading")
                    },
                )
                chunk.metadata["summary"] = ai.summary
                chunk.metadata["keywords"] = ai.keywords
                chunk.metadata["entities"] = [e.model_dump() for e in ai.entities]
            except Exception:
                logger.exception(
                    "Error al enriquecer chunk %s; se guarda sin metadatos de IA.",
                    chunk.metadata.get("chunk_id"),
                )

            enriched.append(chunk)

        save_docs_jsonl_per_file(enriched, gold_dir)
        print(f"  Guardados {len(enriched)} chunks enriquecidos -> {gold_file}")

    print("\n[done] Proceso split_and_enrich completado.")


def main() -> None:
    split_and_enrich_directory()


if __name__ == "__main__":
    main()
