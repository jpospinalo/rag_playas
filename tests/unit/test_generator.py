# tests/unit/test_generator.py
from langchain_core.documents import Document

from rag.core.generator import _build_context_block


def test_build_context_block_formats_docs():
    docs = [
        Document(
            page_content="Texto del chunk 1",
            metadata={"source": "test.pdf", "chunk_id": "test_chunk_0"},
        ),
    ]
    result = _build_context_block(docs)
    assert "doc1" in result
    assert "test.pdf" in result
    assert "Texto del chunk 1" in result


def test_build_context_block_empty():
    result = _build_context_block([])
    assert result == ""
