# rag/core/query_enricher.py
"""Query enrichment step for the RAG pipeline.

Before retrieval, the user's raw query is rewritten into a richer, domain-specific
string that improves both BM25 keyword matching and dense vector search.

The original question is never modified; it continues to be used verbatim in the
final LLM generation prompt.

Configuration (via .env or environment):
    QUERY_ENRICHMENT_ENABLED  – "true" (default) | "false"
    QUERY_ENRICHMENT_HYDE     – "false" (default) | "true"
"""

from __future__ import annotations

import json
import logging
import os
import re

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field, ValidationError

load_dotenv()

logger = logging.getLogger(__name__)

ENRICHMENT_ENABLED: bool = os.getenv("QUERY_ENRICHMENT_ENABLED", "true").lower() == "true"
ENRICHMENT_HYDE: bool = os.getenv("QUERY_ENRICHMENT_HYDE", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Legal concept vocabulary (used in the prompt as a closed-list hint)
# ---------------------------------------------------------------------------

_LEGAL_CONCEPT_LABELS: list[str] = [
    "deslinde_amojonamiento",
    "concesion_permiso",
    "acceso_publico",
    "sancion_administrativa",
    "licencia_ambiental",
    "dominio_publico_bienes_uso_publico",
    "servidumbre_transito",
    "construccion_edificacion",
    "uso_aprovechamiento",
    "competencia_jurisdiccion",
]

# ---------------------------------------------------------------------------
# Pydantic output schema
# ---------------------------------------------------------------------------


class EnrichedQuery(BaseModel):
    """Structured output of the enrichment LLM call."""

    expanded_query: str = Field(
        description=(
            "Cadena de búsqueda enriquecida con términos jurídicos precisos del "
            "derecho colombiano de costas, sinónimos legales e instituciones relevantes."
        )
    )
    legal_concepts: list[str] = Field(
        default_factory=list,
        description="1–3 etiquetas del tipo de problema jurídico identificado.",
    )
    sub_questions: list[str] = Field(
        default_factory=list,
        description=(
            "0–3 sub-preguntas focalizadas que descomponen la consulta en aspectos "
            "jurídicos independientes. Lista vacía si la consulta ya es específica."
        ),
    )
    hyde_passage: str | None = Field(
        default=None,
        description=(
            "Fragmento hipotético de sentencia que podría aparecer en el corpus. "
            "Solo se genera cuando QUERY_ENRICHMENT_HYDE=true."
        ),
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_ENRICHMENT_SYSTEM = """\
Eres un experto en jurisprudencia colombiana sobre playas, zonas costeras, \
dominio público marítimo-terrestre y bienes de uso público.

Tu única tarea es enriquecer consultas jurídicas para mejorar la recuperación \
de documentos en un sistema RAG especializado en sentencias del Consejo de Estado \
y Tribunales Administrativos colombianos. NO respondas la consulta.\
"""

_HYDE_CLAUSE = (
    "\n4. `hyde_passage`: un párrafo breve (3–5 oraciones) que simule un extracto real "
    "de sentencia del Consejo de Estado o Tribunal Administrativo colombiano que respondería "
    "la consulta. Usar terminología y estilo judicial colombiano auténtico.\n"
)


def _build_human_body(include_hyde: bool) -> str:
    """Returns the task instructions block (without the system framing)."""
    concepts = ", ".join(_LEGAL_CONCEPT_LABELS)
    hyde_section = _HYDE_CLAUSE if include_hyde else ""
    return (
        "Dada la siguiente consulta de un abogado, produce un objeto JSON con estos campos:\n\n"
        "1. `expanded_query`: cadena de búsqueda enriquecida (50–120 tokens) que combine "
        "la consulta original con términos jurídicos precisos del derecho colombiano de costas. "
        "Incluye sinónimos legales, nombres de instituciones relevantes (Consejo de Estado, "
        "Tribunal Administrativo, DIMAR, ANLA, Superintendencia de Notariado), "
        "normas clave (Decreto 2811/1974, Ley 99/1993, Código Civil arts. 674-677) "
        "y conceptos directamente relacionados con el problema planteado.\n\n"
        "2. `legal_concepts`: lista de 1–3 etiquetas que clasifiquen el tipo de problema "
        f"jurídico. Elegir únicamente de: {concepts}.\n\n"
        "3. `sub_questions`: 0–3 sub-preguntas focalizadas que descompongan la consulta "
        "en aspectos jurídicos independientes. Omitir (lista vacía) si la consulta "
        "ya es suficientemente específica."
        f"{hyde_section}\n\n"
        "Responde ÚNICAMENTE con el objeto JSON, sin texto adicional ni bloques markdown.\n\n"
        "Consulta: {{question}}"
    )


# ---------------------------------------------------------------------------
# JSON parsing for models that don't support function calling (e.g. Gemma)
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _parse_json_response(text: str, question: str) -> EnrichedQuery:
    """Extract and validate JSON from a plain-text LLM response.

    Strips markdown code fences if the model added them, then validates
    against :class:`EnrichedQuery`. Falls back to the original question
    on any parse or validation error.
    """
    # Strip markdown fences if present
    fence_match = _JSON_FENCE_RE.search(text)
    json_text = fence_match.group(1).strip() if fence_match else text.strip()

    try:
        data = json.loads(json_text)
        result = EnrichedQuery(**data)
        if not result.expanded_query.strip():
            return _fallback(question)
        return result
    except (json.JSONDecodeError, ValidationError, TypeError):
        logger.warning(
            "Failed to parse enrichment JSON response; using fallback.\nRaw output: %s",
            text[:300],
        )
        return _fallback(question)


def _build_prompt_for_model(model_name: str, include_hyde: bool) -> ChatPromptTemplate:
    """Return the appropriate prompt template for *model_name*.

    Gemma models do not support a dedicated system role; instructions are
    folded into the single human turn — the same pattern used in generator.py.
    """
    human_body = _build_human_body(include_hyde)
    model = (model_name or "").lower()
    if model.startswith("gemma-"):
        return ChatPromptTemplate.from_messages(
            [("human", f"INSTRUCCIONES:\n{{instructions}}\n\n{human_body}")]
        ).partial(instructions=_ENRICHMENT_SYSTEM)
    return ChatPromptTemplate.from_messages(
        [
            ("system", _ENRICHMENT_SYSTEM),
            ("human", human_body),
        ]
    )


# ---------------------------------------------------------------------------
# LLM — separate instance from the generation LLM to allow independent caching
# ---------------------------------------------------------------------------


def _get_enrichment_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        temperature=0.0,
    )


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


def _fallback(question: str) -> EnrichedQuery:
    """Return a minimal enriched query using the original question unchanged."""
    return EnrichedQuery(expanded_query=question, legal_concepts=[], sub_questions=[])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _is_gemma(model_name: str) -> bool:
    return (model_name or "").lower().startswith("gemma-")


def enrich_query(question: str) -> EnrichedQuery:
    """Synchronously enrich *question* for better RAG retrieval.

    Gemma models don't support function calling, so JSON is requested via the
    prompt and parsed manually.  Gemini models use ``with_structured_output``.

    If enrichment is disabled or any error occurs, returns a fallback
    :class:`EnrichedQuery` whose ``expanded_query`` equals the original
    question so the pipeline is unaffected.
    """
    if not ENRICHMENT_ENABLED:
        return _fallback(question)

    try:
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        prompt = _build_prompt_for_model(model_name, ENRICHMENT_HYDE)
        llm = _get_enrichment_llm()

        if _is_gemma(model_name):
            raw: str = (prompt | llm | StrOutputParser()).invoke({"question": question})
            return _parse_json_response(raw, question)

        result: EnrichedQuery = (prompt | llm.with_structured_output(EnrichedQuery)).invoke(
            {"question": question}
        )
        if not result.expanded_query.strip():
            logger.warning("Enrichment returned an empty expanded_query; using fallback.")
            return _fallback(question)
        return result
    except Exception:
        logger.warning(
            "Query enrichment failed; falling back to original query.", exc_info=True
        )
        return _fallback(question)


async def enrich_query_async(question: str) -> EnrichedQuery:
    """Async variant of :func:`enrich_query`."""
    if not ENRICHMENT_ENABLED:
        return _fallback(question)

    try:
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        prompt = _build_prompt_for_model(model_name, ENRICHMENT_HYDE)
        llm = _get_enrichment_llm()

        if _is_gemma(model_name):
            raw: str = await (prompt | llm | StrOutputParser()).ainvoke({"question": question})
            return _parse_json_response(raw, question)

        result: EnrichedQuery = await (prompt | llm.with_structured_output(EnrichedQuery)).ainvoke(
            {"question": question}
        )
        if not result.expanded_query.strip():
            logger.warning("Enrichment returned an empty expanded_query; using fallback.")
            return _fallback(question)
        return result
    except Exception:
        logger.warning(
            "Query enrichment failed; falling back to original query.", exc_info=True
        )
        return _fallback(question)
