# Arquitectura del pipeline RAG

```
PDFs (data/raw/)
      │
      ▼ pdf_to_md.py (Docling + OCR + imágenes)
data/bronze/*.md             ← documentos en Markdown limpio con imágenes
data/bronze/images/          ← imágenes extraídas (figuras, tablas)
      │
      ▼ loaders.py (lectura MD + normalize)
data/silver/*.jsonl          ← documentos normalizados por fuente
      │
      ▼ splitter.py (RecursiveCharacterTextSplitter)
data/silver/chunked/*.jsonl  ← chunks con chunk_id y chunk_index
      │
      ▼ enrich.py (Gemini JSON-mode)
data/gold/*.jsonl            ← chunks + summary + keywords + entities
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
