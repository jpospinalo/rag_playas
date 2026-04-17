# RAG Playas

Sistema de **Recuperación Aumentada por Generación (RAG)** especializado en jurisprudencia sobre playas y bienes de uso público en Colombia. Procesa sentencias en PDF, las estructura semánticamente y expone una **API REST** para consultas en lenguaje natural, consumida por un frontend Next.js.

Consulta aquí el [registro de archivos indexados](docs/archivos-indexados.md)

---

## Pipeline de ingesta

![Pipeline de RAG de jurisprudencia](docs/images/pipeline.png)

El pipeline transforma documentos PDF crudos en chunks semánticos listos para embeddings, pasando por tres etapas de ingestión:

### 1. Raw PDF → Clean Markdown

Los PDFs se convierten a Markdown con **Docling** (OCR, tablas e imágenes). Sobre el Markdown resultante se aplica una limpieza exhaustiva: se eliminan encabezados de página, pies de página, numeraciones de folio y cualquier ruido tipográfico que introduzca tokens sin valor semántico. El objetivo es conservar únicamente el contenido sustantivo y la estructura de secciones del documento.

Las imágenes detectadas en el documento se extraen y almacenan en `data/bronze/images/`.

### 2. Divide by Section

El Markdown limpio se segmenta en secciones usando expresiones regulares sobre los encabezados (`#`, `##`, `###`). Cada sección produce un **chunk grande** que contiene únicamente el texto de ese bloque temático.

### 3. Smart Chunking + Enrichment

Cada chunk de sección se subdivide en **subchunks de 200–400 tokens** y **Gemini** genera metadatos enriquecidos sobre cada subchunk:

- Resumen conciso del fragmento.
- Palabras clave jurídicas relevantes.
- Entidades nombradas (personas, lugares, fechas).

El resultado se escribe en `data/gold/`. Este enriquecimiento mejora la precisión del retrieval al inyectar señal semántica explícita en cada chunk antes de calcular el embedding.

Consulta [la lista de archivos ya indexados](docs/archivos-indexados.md) para ver cuáles documentos han sido enriquecidos.

### 4. Embeddings

Los subchunks enriquecidos se vectorizan con **Ollama** (`embeddinggemma`) y se indexan en **ChromaDB**. El retriever combina búsqueda vectorial y BM25 con fusión por RRF (Reciprocal Rank Fusion).

---

## Estructura de los documentos

![Estructura general en documentos](docs/images/estructura-general.png)

| Bloque                     | Secciones habituales                                                                                                                                                                                                                                   |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Contexto del caso**      | Antecedentes · Síntesis del caso · Resumen de la demanda · Petitum · Causa petendi                                                                                                                                                                     |
| **Desarrollo procesal**    | Contestación de la demanda · Actuación procesal · Trámite de la acción · Sentencia de primera instancia · Fallo de primera instancia · Recurso de apelación · Trámite de segunda instancia · Actuaciones posteriores al fallo · Alegatos de conclusión |
| **Argumentación jurídica** | Consideraciones · Consideraciones de la Sala · Consideraciones del tribunal                                                                                                                                                                            |
| **Decisión**               | Conclusiones · Decisión · Falla · Resuelve                                                                                                                                                                                                             |

---

## Arquitectura

El proyecto está dividido en dos paquetes Python independientes más un workspace de frontend:

```
rag_playas/
├── rag/                         # Paquete RAG (API + core)
│   ├── pyproject.toml
│   ├── config.py                ← variables de entorno para el paquete rag
│   ├── core/                    ← lógica RAG
│   │   ├── embeddings.py        ← cliente Ollama compartido
│   │   ├── vectorstore.py       ← construye/actualiza la colección en ChromaDB
│   │   ├── retriever.py         ← BM25 + vectorial + reranker (RRF)
│   │   └── generator.py         ← cadena RAG (retriever + Gemini)
│   └── api/                     ← FastAPI
│       ├── main.py              ← app con rutas /api/query y /api/health
│       └── schemas.py           ← modelos Pydantic de request/response
│
├── ingest/                      # Paquete de ingesta (independiente de rag)
│   ├── pyproject.toml
│   ├── config.py                ← variables de entorno para el paquete ingest
│   ├── pdf_to_md/               ← conversión PDF → Markdown (Docling)
│   ├── loaders.py               ← carga Markdown de bronze → silver (incluye metadatos del CSV)
│   ├── normalize.py             ← limpieza y normalización de metadata
│   ├── sections.py              ← segmentación por secciones
│   ├── splitter_and_enrich.py   ← chunking + enriquecimiento con Gemini (silver → gold)
│   └── utils.py                 ← helpers JSONL
│
├── frontend/                    # Next.js (workspace independiente)
│   └── package.json
│
├── data/
│   ├── raw/                     ← PDFs originales + metadata.csv (metadatos legales)
│   ├── bronze/                  ← Markdown limpio (con imágenes en bronze/images/)
│   ├── silver/                  ← documentos normalizados (JSONL por archivo)
│   └── gold/                    ← chunks enriquecidos (resumen, keywords, entidades)
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── evaluation/
│   ├── ragas_eval_gemma.py
│   └── ragas_eval_ollama.py
│
├── infrastructure/              # Terraform (AWS)
│   ├── terraform.tf
│   ├── providers.tf
│   ├── variables.tf
│   ├── locals.tf
│   ├── main.tf
│   └── outputs.tf
│
├── docs/
├── scripts/
│   ├── ec2_chroma_db.sh
│   ├── ec2_ollama_embeddings.sh
│   └── run_pipeline.sh
│
├── pyproject.toml               ← workspace root uv (dev deps: pytest, ruff, mypy, ragas)
├── package.json                 ← workspace root bun
├── uv.lock
└── Makefile
```

### Gestión de dependencias

| Capa   | Herramienta                                | Archivo principal                                                        |
| ------ | ------------------------------------------ | ------------------------------------------------------------------------ |
| Python | [uv](https://docs.astral.sh/uv/) workspace | `pyproject.toml` (raíz) + `rag/pyproject.toml` + `ingest/pyproject.toml` |
| Node   | [Bun](https://bun.sh/) workspace           | `package.json` (raíz) + `frontend/package.json`                          |

El entorno virtual Python (`.venv`) y los `node_modules` residen en la raíz del proyecto. Los archivos de lock (`uv.lock`, `bun.lock`) también quedan en la raíz.

Los paquetes `rag` e `ingest` son **completamente independientes** entre sí. Cada uno tiene su propio `config.py` que lee únicamente las variables de entorno que necesita, apuntando al único `.env` en la raíz del proyecto.

---

## Compatibilidad

Diseñado para ejecutarse en **Linux**. Los scripts `.sh` asumen `apt-get` y Docker disponibles.

**Windows con WSL** es compatible con conversión previa de saltos de línea:

```bash
sudo apt-get install -y dos2unix
dos2unix scripts/*.sh
```

---

## Requisitos

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) — gestor de dependencias y entornos virtuales
- [Bun](https://bun.sh/) — gestor de paquetes Node (para el frontend)
- Docker — para ChromaDB
- Ollama — para embeddings
- API Key de Google — para **Gemini**

---

## Instalación

```bash
# Instalar uv (una vez)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clonar el repositorio
git clone https://github.com/jpospinalo/rag_playas.git
cd rag_playas

# Instalar todas las dependencias Python (crea .venv en la raíz)
uv sync --group dev

# Copiar y completar las variables de entorno
cp .env.example .env
```

---

## Infraestructura en AWS

Antes de ejecutar el pipeline se necesitan dos instancias EC2. Se recomienda asignar una **IP elástica** a cada una para estabilizar las variables de entorno.

### Opción A — Terraform (recomendado)

La carpeta `infrastructure/` contiene la configuración de Terraform para provisionar ambas máquinas automáticamente:

| Máquina   | Tipo        | Almacenamiento | Puerto | AMI                  |
| --------- | ----------- | -------------- | ------ | -------------------- |
| ChromaDB  | `t3.medium` | 12 GB gp3      | `8000` | Ubuntu Server 24.04  |
| Ollama    | `t3.large`  | 20 GB gp3      | `11434`| Ubuntu Server 24.04  |

Cada instancia tiene una IP elástica asignada y ejecuta su script de setup automáticamente al iniciarse.

Instala Terraform desde [developer.hashicorp.com/terraform/install](https://developer.hashicorp.com/terraform/install), luego:

```bash
cd infrastructure/
terraform init
terraform plan
terraform apply
```

Al terminar, `terraform output` muestra las IPs elásticas para configurar el `.env`.

### Opción B — Setup manual

Si ya tienes las instancias creadas, conéctate a cada una y ejecuta el script correspondiente:

#### EC2 — ChromaDB

```bash
bash scripts/ec2_chroma_db.sh
```

Lanza ChromaDB en Docker con persistencia en `/opt/chroma-data`, expuesto en el puerto `8000`.

#### EC2 — Ollama (embeddings)

```bash
bash scripts/ec2_ollama_embeddings.sh
```

Lanza Ollama en Docker en el puerto `11434` y descarga el modelo `embeddinggemma`.

### Variables de entorno

```dotenv
# ChromaDB (EC2)
CHROMA_HOST=<ip-elastica-chroma>
CHROMA_PORT=8000
CHROMA_COLLECTION_NAME=rag_playas

# Ollama (EC2)
OLLAMA_EMBED_BASE_URLL=http://<ip-elastica-ollama>:11434
OLLAMA_EMBED_MODEL=embeddinggemma

# Gemini
GOOGLE_API_KEY=<tu-api-key>
GEMINI_MODEL=gemini-2.0-flash
```

> Los grupos de seguridad deben permitir tráfico entrante en los puertos `8000` y `11434` desde la IP de la máquina que ejecuta el pipeline.

---

## Ejecución del pipeline

Cada paso puede ejecutarse individualmente o todos de un solo comando:

```bash
# 1) PDF → Markdown limpio          →  data/bronze/
uv run python -m ingest.pdf_to_md

# 2) Normalización + secciones + metadatos CSV →  data/silver/
uv run python -m ingest.loaders

# 3) Chunking + enriquecimiento     →  data/gold/
uv run python -m ingest.splitter_and_enrich

# 4) Indexar en ChromaDB
uv run python -m rag.core.vectorstore

# 5) Lanzar la API FastAPI
uv run uvicorn rag.api.main:app --reload --port 8080
```

O ejecutar todo de un solo comando:

```bash
bash scripts/run_pipeline.sh
```

La API queda disponible en `http://localhost:8080`. Endpoints:

| Método | Ruta          | Descripción                             |
| ------ | ------------- | --------------------------------------- |
| `GET`  | `/api/health` | Liveness check                          |
| `POST` | `/api/query`  | Consulta jurídica → respuesta + fuentes |

Ejemplo de request:

```json
POST /api/query
{
  "question": "¿Cuál es el criterio del Tribunal Supremo sobre el deslinde del dominio público marítimo-terrestre?",
  "k": 4,
  "k_candidates": 8
}
```

---

## Comandos útiles

```bash
make install        # instalar dependencias
make lint           # verificar estilo con ruff
make format         # formatear código
make typecheck      # verificar tipos con mypy
make test           # tests unitarios
make test-cov       # tests + cobertura
make pipeline       # ejecutar pipeline completo de ingesta
make app            # lanzar la API FastAPI
make frontend       # lanzar frontend con NextJS
make help           # ver todos los comandos
```
