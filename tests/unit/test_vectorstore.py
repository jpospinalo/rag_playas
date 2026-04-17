# tests/unit/test_vectorstore.py
import json
from unittest.mock import patch

from rag.core.vectorstore import load_gold_records, sanitize_metadata


def test_sanitize_metadata_preserves_primitives():
    meta = {"key_str": "value", "key_int": 42, "key_float": 3.14, "key_bool": True}
    result = sanitize_metadata(meta)
    assert result == meta


def test_sanitize_metadata_converts_lists():
    meta = {"keywords": ["jurisprudencia", "amparo"]}
    result = sanitize_metadata(meta)
    assert isinstance(result["keywords"], str)
    assert "jurisprudencia" in result["keywords"]


def test_sanitize_metadata_converts_dicts():
    meta = {"nested": {"a": 1}}
    result = sanitize_metadata(meta)
    assert isinstance(result["nested"], str)


def test_load_gold_records_reads_jsonl_records_from_s3():
    records = [
        {
            "page_content": "Texto de doctrina aplicable.",
            "metadata": {
                "chunk_id": "exp_001_chunk_0",
                "source": "exp_001.pdf",
                "keywords": ["doctrina", "civil"],
            },
        },
        {
            "page_content": " ",
            "metadata": {"chunk_id": "empty_chunk"},
        },
    ]
    jsonl_content = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"

    with patch("rag.core.vectorstore.read_text", return_value=jsonl_content):
        ids, texts, embed_texts, metadatas = load_gold_records("gold/expediente.jsonl")

    assert ids == ["exp_001_chunk_0"]
    assert texts == ["Texto de doctrina aplicable."]
    assert len(embed_texts) == 1
    assert metadatas[0]["source"] == "exp_001.pdf"
    assert "keywords_str" in metadatas[0]
