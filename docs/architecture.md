# Arquitectura del pipeline RAG

```
PDFs (data/raw/)
      │
      ▼ pdf_to_md (Docling + OCR + imágenes)
data/bronze/*.md             ← documentos en Markdown limpio con imágenes
data/bronze/<doc>/assets/    ← imágenes extraídas (figuras, tablas)
      │
      ▼ loaders.py (lectura MD + normalize + split_by_sections)
data/silver/*.jsonl          ← secciones normalizadas (4 por documento)
      │
      ▼ splitter_and_enrich.py (chunking + Gemini JSON-mode)
data/gold/*.jsonl            ← chunks con chunk_id, summary, keywords, entities
      │
      ▼ vectorstore.py (Ollama embeddings → ChromaDB)
ChromaDB (HTTP)              ← colección indexada
      │
      ▼ retriever.py (BM25 + Dense → RRF → Reranker)
top-k docs
      │
      ▼ generator.py (LCEL chain → Gemini)
respuesta final              ← mostrada en Gradio
```
