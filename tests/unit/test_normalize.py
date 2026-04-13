# tests/unit/test_normalize.py
import pytest
from langchain_core.documents import Document

from ingest.normalize import normalize_documents, normalize_metadata, normalize_text


def test_normalize_text_collapses_blank_lines_to_max_two():
    result = normalize_text("Línea 1\n\n\nLínea 2")
    assert "Línea 1" in result
    assert "Línea 2" in result
    assert "\n\n\n" not in result


def test_normalize_text_strips_trailing_whitespace():
    text = "Linea con espacios   \nOtra linea\t\t"
    result = normalize_text(text)
    assert result == "Linea con espacios\nOtra linea"


@pytest.mark.parametrize(
    ("source", "expected_source", "expected_title"),
    [
        ("sentencia_corte_suprema.pdf", "sentencia_corte_suprema.pdf", "sentencia corte suprema"),
        ("/tmp/casos/fallo_123.txt", "fallo_123.txt", "fallo 123"),
        ("resolucion_general", "resolucion_general", "resolucion general"),
    ],
)
def test_normalize_metadata_uses_filename_and_humanized_stem(
    source: str,
    expected_source: str,
    expected_title: str,
):
    meta = {"source": source, "extra": "ignored"}
    result = normalize_metadata(meta)
    assert result["source"] == expected_source
    assert result["title"] == expected_title
    assert "extra" not in result


def test_normalize_documents_applies_text_and_metadata_normalization(sample_document):
    result = normalize_documents([sample_document])
    assert len(result) == 1
    assert result[0].page_content == sample_document.page_content
    assert result[0].metadata["source"] == sample_document.metadata["source"]
    assert "title" in result[0].metadata


def test_normalize_documents_returns_new_document_instances(sample_document):
    result = normalize_documents([sample_document])
    assert all(isinstance(d, Document) for d in result)
    assert result[0] is not sample_document
