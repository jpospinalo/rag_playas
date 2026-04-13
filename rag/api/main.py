"""FastAPI application for the RAG Playas legal jurisprudence system.

Replaces the Gradio interface with a REST API consumed by the Next.js frontend.

Run with:
    uv run uvicorn rag.api.main:app --reload --port 8080
"""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.documents import Document

from rag.api.schemas import QueryRequest, QueryResponse, SourceDocument
from rag.core.generator import generate_answer, generate_answer_stream
from rag.core.retriever import init_retrievers

# ── Lifespan ───────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Pre-calienta los componentes costosos al arrancar:
      - Conexión HTTP a Chroma (singleton)
      - Índice BM25 completo (construido una sola vez desde el corpus de Chroma)
      - Vectorstore LangChain-Chroma (singleton)

    Esto elimina la penalización de arranque en la primera petición.
    """
    import asyncio

    await asyncio.to_thread(init_retrievers)
    yield


# ── App ────────────────────────────────────────────────────────────────────


app = FastAPI(
    title="RAG Playas API",
    description="Sistema de consulta de jurisprudencia española en materia de playas",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _clean_answer(answer: str) -> str:
    """Remove trailing citation suffixes added by some LLM configurations."""
    patterns = [
        r"\s*\(fuente:[^)]+\)\s*$",
        r"\s*\((?:doc|chunk)[^)]*\)\s*$",
    ]
    for p in patterns:
        answer = re.sub(p, "", answer)
    return answer.strip()


def _doc_to_source(doc: Document) -> SourceDocument:
    meta = doc.metadata or {}
    content = (doc.page_content or "").strip().replace("\n", " ")
    if len(content) > 500:
        content = content[:500] + "..."

    title = meta.get("title") or meta.get("book_title") or ""
    if not title:
        source_path = meta.get("source", "")
        title = Path(source_path).stem.replace("_", " ") if source_path else ""

    return SourceDocument(
        content=content,
        source=meta.get("source", ""),
        title=title,
        metadata={k: v for k, v in meta.items() if k not in ("source",)},
    )


# ── Routes ─────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict:
    """Liveness check."""
    return {"status": "ok"}


@app.post("/api/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    """
    Submit a legal question and receive a RAG-generated answer with source fragments.

    The retriever performs hybrid BM25 + vector search (in parallel) before
    feeding the top-k documents as context to the Gemini LLM.
    Uses a single retrieval pass — no duplicate retriever invocations.
    """
    try:
        answer_raw, docs, enriched_query = generate_answer(
            question=request.question,
            k=request.k,
            k_candidates=request.k_candidates,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return QueryResponse(
        answer=_clean_answer(answer_raw),
        sources=[_doc_to_source(d) for d in docs],
        enriched_query=enriched_query,
    )


@app.post("/api/query/stream")
async def query_stream(request: QueryRequest):
    """
    SSE streaming endpoint: emite tokens del LLM en tiempo real y envía
    los documentos fuente como evento final antes de cerrar el stream.

    Formato de eventos SSE:
      data: {"type": "token",   "content": "<fragmento>"}
      data: {"type": "sources", "sources": [...]}
      data: [DONE]

    El retriever se invoca una sola vez antes de iniciar el streaming.
    """

    async def event_generator():
        try:
            async for token, docs, enriched_query in generate_answer_stream(
                question=request.question,
                k=request.k,
                k_candidates=request.k_candidates,
            ):
                if docs is None:
                    payload = json.dumps({"type": "token", "content": token})
                    yield f"data: {payload}\n\n"
                else:
                    sources = [_doc_to_source(d).model_dump() for d in docs]
                    payload = json.dumps(
                        {
                            "type": "sources",
                            "sources": sources,
                            "enriched_query": enriched_query,
                        }
                    )
                    yield f"data: {payload}\n\n"
                    yield "data: [DONE]\n\n"
        except Exception as exc:
            payload = json.dumps({"type": "error", "detail": str(exc)})
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
