# tests/integration/test_full_pipeline.py
import pytest
from langchain_core.documents import Document


@pytest.mark.integration
def test_generate_answer_contract_returns_trimmed_answer_and_top_k_docs(monkeypatch):
    from rag.core import generator

    docs = [
        Document(page_content="Hecho relevante 1", metadata={"chunk_id": "a"}),
        Document(page_content="Hecho relevante 2", metadata={"chunk_id": "b"}),
        Document(page_content="Hecho relevante 3", metadata={"chunk_id": "c"}),
    ]

    class FakeChain:
        def invoke(self, _: str) -> str:
            return "  Respuesta sintetica basada en contexto.  "

    class FakeRetriever:
        def invoke(self, _: str):
            return docs

    monkeypatch.setattr(
        generator, "build_rag_chain", lambda k_candidates=8: (FakeChain(), FakeRetriever())
    )

    answer, used_docs = generator.generate_answer("Consulta de prueba", k=2, k_candidates=5)

    assert answer == "Respuesta sintetica basada en contexto."
    assert len(used_docs) == 2
    assert used_docs == docs[:2]


@pytest.mark.integration
def test_generate_answer_contract_returns_fallback_when_no_answer_and_no_docs(monkeypatch):
    from rag.core import generator

    class FakeChain:
        def invoke(self, _: str) -> str:
            return ""

    class FakeRetriever:
        def invoke(self, _: str):
            return []

    monkeypatch.setattr(
        generator, "build_rag_chain", lambda k_candidates=8: (FakeChain(), FakeRetriever())
    )

    answer, used_docs = generator.generate_answer("Consulta sin evidencia", k=3, k_candidates=6)

    assert answer == "No se encontraron fragmentos relevantes en la base de conocimiento."
    assert used_docs == []
