# RAG Playas

Sistema de **Recuperación Aumentada por Generación (RAG)** sobre documentos jurídicos.

- Conversión de PDFs a Markdown limpio con **Docling** (OCR, tablas, imágenes).
- Ingesta y normalización de Markdown a JSONL.
- Chunking y enriquecimiento semántico con **Gemini**.
- Indexación vectorial en **ChromaDB** usando embeddings de **Ollama**.
- Interfaz de chat en **Gradio**.

---

## Estructura del proyecto

```
rag_playas/
├── pyproject.toml
├── uv.lock
├── .python-version
├── .env.example
├── Makefile
│
├── data/
│   ├── raw/             ← PDFs originales
│   ├── bronze/          ← Markdown limpio (con imágenes en bronze/images/)
│   ├── silver/          ← documentos normalizados (JSONL por archivo)
│   │   └── chunked/     ← chunks para RAG
│   └── gold/            ← chunks enriquecidos (resumen, keywords, entidades)
│
├── src/
│   ├── config.py        ← configuración centralizada desde variables de entorno
│   ├── ingest/
│   │   ├── pdf_to_md.py ← convierte PDFs (raw) a Markdown (bronze)
│   │   ├── loaders.py   ← carga Markdown de bronze y genera capa silver
│   │   ├── normalize.py ← limpieza y normalización de metadata
│   │   ├── splitter.py  ← divide documentos en chunks
│   │   └── enrich.py    ← enriquece chunks con Gemini (capa gold)
│   ├── backend/
│   │   ├── embeddings.py   ← cliente Ollama compartido
│   │   ├── vectorstore.py  ← construye/actualiza la colección en Chroma
│   │   ├── retriever.py    ← BM25 + vectorial + reranker (RRF)
│   │   └── generator.py    ← cadena RAG (retriever + Gemini)
│   └── frontend/
│       └── gradio_app.py   ← interfaz de chat
│
├── scripts/
│   ├── ec2_chroma_db.sh
│   ├── ec2_ollama_embeddings.sh
│   └── run_pipeline.sh     ← pipeline completo de un solo comando
│
├── tests/
│   ├── unit/
│   └── integration/
│
└── evaluation/
    ├── ragas_eval_gemma.py
    └── ragas_eval_ollama.py
```

---

## Compatibilidad

Este proyecto está diseñado para ejecutarse en **Linux**. Los scripts de shell (`.sh`) asumen un entorno Linux con `apt-get` y Docker disponibles.

**Windows con WSL** es compatible, pero requiere configuración adicional: los scripts deben convertirse a formato Unix antes de ejecutarse, ya que Git en Windows puede introducir saltos de línea `\r\n` que causan errores:

```bash
sudo apt-get install -y dos2unix
dos2unix scripts/*.sh
```

---

## Requisitos

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) (gestor de dependencias y entornos)
- Docker (para ChromaDB)
- Ollama (para embeddings y reranking)
- API Key de Google para **Gemini**

---

## Instalación

```bash
# Instalar uv (una vez)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clonar el repositorio
git clone https://github.com/jpospinalo/poe_rag.git
cd poe_rag

# Instalar dependencias (crea .venv automáticamente)
uv sync

# Instalar también dependencias de desarrollo
uv sync --dev

# Copiar y completar las variables de entorno
cp .env.example .env
```

---

## Infraestructura en AWS (previo al pipeline)

Antes de ejecutar el pipeline se necesitan dos instancias EC2 en AWS. Se recomienda asignar una **IP elástica** a cada una para que las variables de entorno sean estables.

### EC2 — ChromaDB

En la instancia destinada a ChromaDB, ejecutar `scripts/ec2_chroma_db.sh`:

```bash
bash scripts/ec2_chroma_db.sh
```

Lanza ChromaDB en Docker con persistencia en `/opt/chroma-data`, expuesto en el puerto `8000`.

### EC2 — Ollama (embeddings)

En la instancia destinada a Ollama, ejecutar `scripts/ec2_ollama_embeddings.sh`:

```bash
bash scripts/ec2_ollama_embeddings.sh
```

Lanza Ollama en Docker, expuesto en el puerto `11434`, y descarga el modelo `embeddinggemma`.

### Variables de entorno

Una vez levantadas las instancias, configurar `.env` con las IPs elásticas correspondientes:

```dotenv
# ChromaDB (EC2)
CHROMA_HOST=<ip-elastica-chroma>
CHROMA_PORT=8000
CHROMA_COLLECTION=poe_rag

# Ollama (EC2)
OLLAMA_BASE_URL=http://<ip-elastica-ollama>:11434
OLLAMA_EMBEDDING_MODEL=embeddinggemma
```

> Asegurarse de que los grupos de seguridad de cada instancia permiten tráfico entrante en los puertos `8000` (Chroma) y `11434` (Ollama) desde la IP de la máquina que ejecuta el pipeline.

---

## Pipeline

```bash
# 1) Conversión PDF → Markdown → data/bronze/
uv run python -m src.ingest.pdf_to_md

# 2) Ingesta y normalización → data/silver/
uv run python -m src.ingest.loaders

# 3) Chunking → data/silver/chunked/
uv run python -m src.ingest.splitter

# 4) Enriquecimiento con Gemini → data/gold/
uv run python -m src.ingest.enrich

# 5) Indexar en ChromaDB
uv run python -m src.backend.vectorstore

# 6) Lanzar la interfaz Gradio
uv run python -m src.frontend.gradio_app
```

O ejecutar el pipeline completo:

```bash
bash scripts/run_pipeline.sh
```

La interfaz queda disponible en `http://0.0.0.0:7860`.

---

## Comandos útiles (Makefile)

```bash
make install        # instalar dependencias
make lint           # verificar estilo con ruff
make format         # formatear código
make test           # tests unitarios
make test-cov       # tests + cobertura
make pipeline       # ingestar documentos
make app            # lanzar Gradio
make help           # ver todos los comandos
```
