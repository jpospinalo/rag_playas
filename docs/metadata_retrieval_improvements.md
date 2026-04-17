# Mejoras de recuperación mediante metadatos

## Resumen ejecutivo

El pipeline de ingesta extrae y enriquece con IA metadatos ricos para cada chunk (corporación, magistrado, tema, sección, resumen, keywords, entidades). Sin embargo, el pipeline de recuperación original ignoraba casi todos estos campos. Este documento describe tres mejoras implementadas para aprovecharlos en la recuperación y generación, y una cuarta pendiente de evaluación.

---

## Metadatos disponibles por chunk

Cada documento en ChromaDB contiene los siguientes campos de metadatos, producidos en distintas etapas del pipeline:

| Campo | Origen | Ejemplo |
|-------|--------|---------|
| `source` | Nombre del archivo | `AP Miguel Ángel Enciso VS Distrito y otros.md` |
| `title` | Normalización (ingest) | `AP Miguel Ángel Enciso VS Distrito y otros` |
| `chunk_id` | Vectorstore | `AP Miguel Ángel Enciso..._s2_c3` |
| `section_index` | `ingest/sections.py` | `2` |
| `section_name` | `ingest/sections.py` | `Argumentación jurídica` |
| `section_heading` | `ingest/sections.py` | `CONSIDERACIONES DE LA SALA` |
| `chunk_index` | `ingest/splitter_and_enrich.py` | `3` |
| `Corporación` | CSV (`data/raw/metadata.csv`) | `Tribunal Administrativo del Magdalena` |
| `Radicado` | CSV | `47-001-3333-001-2016-03261` |
| `Magistrado ponente` | CSV | `Maribel Mendoza Jiménez` |
| `Partes procesales` | CSV | `Accionante: Miguel Ángel Enciso Pava...` |
| `Tema principal` | CSV | `Alteración del cauce del río Gaira` |
| `TEMATICA` | CSV | `Ambiental` |
| `RELACIÓN PLAYAS` | CSV | `Indirecta` |
| `summary` | Gemini (AI enrichment) | Descripción de ~40 palabras del chunk |
| `keywords_str` | Gemini → vectorstore | `deslinde, zona costera, bienes de uso público, DIMAR` |
| `entities` | Gemini (AI enrichment) | JSON string con entidades PERSON, ORG, LAW, etc. |

---

## Mejoras implementadas

### P0 — Contextual Chunk Headers en los embeddings

**Archivo:** `rag/core/vectorstore.py`  
**Funciones:** `_build_embedding_text()` (nueva), `load_gold_records()`, `build_or_load_vectorstore()`

#### Problema

Los embeddings se generaban únicamente del `page_content`. Un chunk cuyo texto dice "la Sala consideró que..." tenía un vector que no capturaba su contexto jurídico real (qué tribunal, qué tema, qué sección). Queries como "¿qué criterio usó el Tribunal del Magdalena sobre deslinde?" podían no encontrar ese chunk aunque fuera el más relevante.

#### Solución

Antes de generar el embedding, se construye un texto aumentado que antepone los metadatos clave al `page_content`:

```
Sección: Argumentación jurídica
Tema principal: Alteración del cauce del río Gaira y ocupación de zona de playa
Palabras clave: deslinde, amojonamiento, zona costera, DIMAR, bienes de uso público
Resumen: El tribunal analiza la procedencia del deslinde sobre zona de playa pública.

[page_content original aquí]
```

El vector se genera desde este texto aumentado, pero **ChromaDB almacena solo el `page_content` original** como documento. El LLM recibe el texto limpio; el enriquecimiento contextual queda solo en el espacio vectorial.

#### Impacto

- Las queries semánticas sobre corporaciones, temas o secciones específicas encontrarán chunks relevantes aunque el término exacto no aparezca en el `page_content`.
- Mejora especialmente para queries multi-atributo ("decisión del Consejo de Estado sobre concesión en zona costera").
- **Requiere re-indexación** (ver sección al final).

---

### P1 — Contexto enriquecido para el LLM

**Archivo:** `rag/core/generator.py`  
**Función:** `_build_context_block()`

#### Problema

El LLM recibía solo `source` y `chunk_id` como metadatos de cada fragmento:

```
[doc1 | source=AP Miguel... | chunk_id=AP Miguel..._s2_c3]
La Sala considera que el deslinde de la zona...
```

Pero `BASE_INSTRUCTIONS` le exige citar magistrados, expedientes y jurisdicción — información que nunca recibía.

#### Solución

Cada bloque de contexto ahora incluye los campos de atribución relevantes:

```
[doc1 | source=AP Miguel... | chunk_id=AP Miguel..._s2_c3]
Corporación: Tribunal Administrativo del Magdalena
Magistrado ponente: Maribel Mendoza Jiménez
Tema principal: Alteración del cauce del río Gaira
Sección: Argumentación jurídica
Resumen: El tribunal analiza la procedencia del deslinde...

La Sala considera que el deslinde de la zona...
```

#### Impacto

- El LLM puede producir respuestas como "el Tribunal Administrativo del Magdalena, con ponencia de la magistrada Mendoza Jiménez, estableció que... [doc1]" en lugar de atribuciones genéricas.
- El `summary` de 40 palabras da señal temática al LLM antes de procesar el texto completo, mejorando la síntesis jurisprudencial.
- Cambio de riesgo cero: solo amplía el bloque de texto; no altera firma ni flujo.
- **No requiere re-indexación.**

---

### P2 — BM25 aumentado con keywords y summary

**Archivo:** `rag/core/retriever.py`  
**Función:** `_get_bm25_base()`

#### Problema

El índice BM25 se construía indexando solo `page_content`. Los `keywords` curados por Gemini (campo `keywords_str`, ej. `"deslinde, amojonamiento, zona costera, DIMAR"`) no participaban en el scoring. Una query con terminología jurídica precisa podía fallar si el chunk usaba lenguaje procesal genérico aunque fuera semánticamente relevante.

#### Solución

El corpus BM25 se construye con texto aumentado: `page_content + keywords_str + summary`. Los documentos retornados conservan el `page_content` original sin modificaciones.

```python
# Corpus de indexación: aumentado
"La Sala considera que... deslinde, amojonamiento, zona costera, DIMAR El tribunal analiza..."

# Documento retornado: limpio
"La Sala considera que..."
```

#### Impacto

- Mejora el recall BM25 para queries con terminología legal específica que coincide con los keywords curados por Gemini.
- BM25 aporta 30% del peso en la fusión RRF del `HybridEnsembleRetriever` — la mejora se propaga al retriever ensemble completo.
- El índice se preconstruye una sola vez en `init_retrievers()` al arrancar la app.
- **No requiere re-indexación.**

---

## P3 — Filtrado vectorial por `legal_concepts` (pendiente)

`EnrichedQuery.legal_concepts` se genera en `query_enricher.py` pero se descarta en `generate_answer()`. Mapear estos conceptos al campo `TEMATICA` de ChromaDB permitiría restringir la búsqueda vectorial.

**Razón para posponer:** el corpus actual solo tiene 2 valores en `TEMATICA` ("Ambiental", "Gestión del riesgo") y ~37% de los chunks no tienen valor. Un filtro duro degradaría el recall. Evaluar cuando el corpus crezca con mayor variedad temática.

---

## Re-indexación (necesaria para P0)

P1 y P2 son efectivos inmediatamente al reiniciar la API. P0 requiere regenerar los embeddings con los textos aumentados.

**Pasos:**

```python
# 1. Eliminar la colección existente (desde Python REPL con acceso al EC2)
import chromadb, os
from dotenv import load_dotenv
load_dotenv()

client = chromadb.HttpClient(
    host=os.getenv("CHROMA_HOST"),
    port=int(os.getenv("CHROMA_PORT", "8000"))
)
client.delete_collection(os.getenv("CHROMA_COLLECTION_NAME"))
```

```bash
# 2. Re-indexar desde cero
uv run python -m rag.core.vectorstore
```

La operación procesa los archivos GOLD en `data/gold/` en orden lexicográfico. Con el Ollama remoto en EC2 y los ~1.871 chunks actuales, el tiempo estimado es similar al de la indexación inicial.
