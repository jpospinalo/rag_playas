# tests/unit/test_vectorstore.py
import json

from rag.core.vectorstore import load_gold_documents, sanitize_metadata


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


def test_load_gold_documents_reads_jsonl_records_from_tmp_dir(tmp_path):
    gold_dir = tmp_path / "gold"
    gold_dir.mkdir()
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
    with (gold_dir / "expediente.jsonl").open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    ids, texts, metadatas = load_gold_documents(str(gold_dir))

    assert ids == ["exp_001_chunk_0"]
    assert texts == ["Texto de doctrina aplicable."]
    assert metadatas[0]["source"] == "exp_001.pdf"
    assert "keywords_str" in metadatas[0]
