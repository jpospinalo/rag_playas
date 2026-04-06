# src/frontend/gradio_app.py

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import gradio as gr
from dotenv import load_dotenv
from langchain_core.documents import Document

from src.backend.generator import generate_answer

load_dotenv()


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------


def format_context(docs: list[Document]) -> str:
    """
    Devuelve un texto en Markdown con el contenido de los chunks recuperados.
    Solo muestra page_content, recortado a 500 caracteres por fragmento.
    """
    if not docs:
        return "No se encontraron fragmentos de contexto."

    partes: list[str] = []
    for i, d in enumerate(docs, start=1):
        texto = (d.page_content or "").strip().replace("\n", " ")
        if len(texto) > 500:
            texto = texto[:500] + "..."
        partes.append(f"**Fragmento {i}**\n{texto}")

    return "\n\n---\n\n".join(partes)


def format_sources(docs: list[Document]) -> str:
    """
    Construye el bloque 'Fuentes' mostrando solo una fuente
    (el primer título encontrado en los metadatos).
    """
    if not docs:
        return ""

    title: str | None = None

    for d in docs:
        meta = d.metadata or {}

        # Intentar obtener un título legible
        title = meta.get("title") or meta.get("book_title")
        if not title:
            source = meta.get("source", "")
            if source:
                stem = Path(source).stem
                title = stem.replace("_", " ")
            else:
                title = "Título desconocido"

        if title:
            break

    if not title:
        return ""

    return f"Fuentes:\n- {title}"


def clean_answer(answer: str) -> str:
    """
    Elimina sufijos tipo '(fuente: ...)' o '(doc2, doc3, ...)' al final de la respuesta.
    """
    if not answer:
        return answer

    patterns = [
        r"\s*\(fuente:[^)]+\)\s*$",  # (fuente: doc1, doc2)
        r"\s*\((?:doc|chunk)[^)]*\)\s*$",  # (doc2, doc3) o (chunk_3, chunk_4)
    ]
    for p in patterns:
        answer = re.sub(p, "", answer)

    return answer.strip()


def respond(
    user_message: str,
    k: int,
    k_candidates: int,
    show_context: bool,
    history: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], str]:
    """
    Función principal de respuesta para Gradio.

    history es una lista de mensajes en formato:
        [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
    """
    if not user_message or not user_message.strip():
        return history or [], ""

    if history is None:
        history = []

    # Llamar al pipeline RAG
    answer_raw, docs = generate_answer(
        question=user_message,
        k=int(k),
        k_candidates=int(k_candidates),
    )

    # Limpiar respuesta y construir bloque de fuentes
    answer = clean_answer(answer_raw)
    sources_block = format_sources(docs)

    if sources_block:
        display_answer = f"{answer}\n\n{sources_block}"
    else:
        display_answer = answer

    # Actualizar historial en formato messages
    history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": display_answer},
    ]

    ctx_text = format_context(docs) if show_context else ""

    return history, ctx_text


# ---------------------------------------------------------------------
# Construcción de la app
# ---------------------------------------------------------------------


def build_app() -> gr.Blocks:
    with gr.Blocks(title="RAG Jurisprudencia — Derecho de Playas") as demo:
        gr.Markdown(
            """
# RAG de Jurisprudencia — Derecho de Playas

Sistema de consulta basado en recuperación semántica (**RAG**) sobre un corpus de
**jurisprudencia española en materia de playas**: sentencias del Tribunal Supremo,
Audiencias Nacionales y Tribunales Superiores de Justicia que abordan el deslinde
del dominio público marítimo-terrestre, servidumbres de tránsito y protección,
concesiones y autorizaciones en zona costera, responsabilidad patrimonial de la
Administración por actuaciones en litoral, y acceso público a la playa.

> Escribe tu pregunta en lenguaje natural. El sistema recupera los fragmentos de
> resoluciones judiciales más relevantes y genera una respuesta fundamentada en ellos.
"""
        )

        with gr.Row():
            # Columna izquierda: chat + controles
            with gr.Column(scale=1):
                chatbot = gr.Chatbot(
                    label="Asistente de jurisprudencia — Playas",
                    height=380,
                    value=[],
                )

                question = gr.Textbox(
                    label="Consulta jurídica",
                    placeholder=(
                        "Por ejemplo: ¿Cuál es el criterio del Tribunal Supremo "
                        "sobre el deslinde del dominio público marítimo-terrestre?"
                    ),
                    lines=2,
                )

                # Controles de recuperación en un acordeón
                with gr.Accordion("Parámetros de recuperación", open=False):
                    k_slider = gr.Slider(
                        minimum=1,
                        maximum=8,
                        value=4,
                        step=1,
                        label="Número de fragmentos para el contexto (k)",
                    )

                    k_candidates_slider = gr.Slider(
                        minimum=4,
                        maximum=16,
                        value=8,
                        step=1,
                        label="Candidatos iniciales del retriever (k_candidates)",
                    )

                    show_context_chk = gr.Checkbox(
                        value=True,
                        label="Mostrar fragmentos recuperados en la columna derecha",
                    )

                send_btn = gr.Button("Consultar", variant="primary")

            # Columna derecha: contexto
            with gr.Column(scale=1):
                gr.Markdown("### Fragmentos recuperados del corpus")
                gr.Markdown(
                    "Aquí se muestran los extractos de las resoluciones judiciales que el "
                    "sistema ha utilizado como contexto para elaborar la respuesta."
                )
                context_md = gr.Markdown(
                    "Todavía no se han recuperado fragmentos. Formula una consulta para verlos."
                )

        # Eventos
        send_btn.click(
            fn=respond,
            inputs=[question, k_slider, k_candidates_slider, show_context_chk, chatbot],
            outputs=[chatbot, context_md],
        )

        question.submit(
            fn=respond,
            inputs=[question, k_slider, k_candidates_slider, show_context_chk, chatbot],
            outputs=[chatbot, context_md],
        )

    return demo


if __name__ == "__main__":
    app = build_app()
    app.launch(server_name="0.0.0.0", server_port=7860, theme="soft")
