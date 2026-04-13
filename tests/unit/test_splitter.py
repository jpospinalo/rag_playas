# tests/unit/test_splitter.py
from langchain_core.documents import Document

from ingest.splitter_and_enrich import _build_splitter, _chunk_section


def _section_doc(source: str = "sentencia_2024.pdf", section_index: int = 1) -> Document:
    return Document(
        page_content="Sentencia de prueba. Fundamentos juridicos para validacion.",
        metadata={
            "source": source,
            "section_index": section_index,
            "section_name": "Contexto del caso",
        },
    )


def test_chunk_section_sets_required_metadata():
    doc = _section_doc()
    splitter = _build_splitter(chunk_size=1000, chunk_overlap=200)
    chunks = _chunk_section(doc, splitter)

    assert chunks
    assert all("chunk_id" in c.metadata for c in chunks)
    assert all("chunk_index" in c.metadata for c in chunks)
    assert all("total_chunks_in_section" in c.metadata for c in chunks)
    assert all(c.metadata["source"] == doc.metadata["source"] for c in chunks)
    assert all(c.page_content.strip() for c in chunks)


def test_chunk_section_indexes_sequentially():
    text = " ".join([f"Parrafo {i}" for i in range(80)])
    doc = Document(
        page_content=text,
        metadata={"source": "sentencia_larga.pdf", "section_index": 2},
    )
    splitter = _build_splitter(chunk_size=120, chunk_overlap=10)
    chunks = _chunk_section(doc, splitter)

    assert len(chunks) > 1
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))
    assert len({c.metadata["chunk_id"] for c in chunks}) == len(chunks)


def test_chunk_section_chunk_id_encodes_section():
    doc = _section_doc(source="fallo_2024.md", section_index=3)
    splitter = _build_splitter(chunk_size=1000, chunk_overlap=200)
    chunks = _chunk_section(doc, splitter)

    for chunk in chunks:
        assert chunk.metadata["chunk_id"].startswith("fallo_2024_s3_c")


def test_chunk_section_total_chunks_consistent():
    text = " ".join([f"Parrafo {i}" for i in range(80)])
    doc = Document(
        page_content=text,
        metadata={"source": "test.pdf", "section_index": 1},
    )
    splitter = _build_splitter(chunk_size=120, chunk_overlap=10)
    chunks = _chunk_section(doc, splitter)

    total = chunks[0].metadata["total_chunks_in_section"]
    assert total == len(chunks)
    assert all(c.metadata["total_chunks_in_section"] == total for c in chunks)


def test_chunk_section_inherits_section_metadata():
    doc = _section_doc()
    splitter = _build_splitter(chunk_size=1000, chunk_overlap=200)
    chunks = _chunk_section(doc, splitter)

    for chunk in chunks:
        assert chunk.metadata.get("section_index") == 1
        assert chunk.metadata.get("section_name") == "Contexto del caso"
