# RAG Quality Analysis — rag_playas

> **Date**: April 2026  
> **Scope**: Full pipeline — ingestion → retrieval → generation → evaluation  
> **Goal**: Identify quality improvements for the RAG system, not performance/speed

---

## TLDR — Resumen de Mejoras Prioritarias

| # | Mejora | Impacto | Esfuerzo |
|---|--------|---------|----------|
| 1 | **Eliminar `_clean_answer`** (destruye citations) | 🔴 Crítico | Muy bajo |
| 2 | **Cambiar separador `.` en chunking** (fragmenta "Art. 142.3") | 🔴 Crítico | Muy bajo |
| 3 | **Eliminar `remove_internal_references()`** (pérdida de jurisprudencia) | 🔴 Crítico | Bajo |
| 4 | **Crear dataset de evaluación real** (actualmente es de Poe) | 🔴 Crítico | Medio |
| 5 | **Aumentar `DEFAULT_K`** de 3 → 5-8 | 🟠 Alto | Muy bajo |
| 6 | **Bajar `RRF c`** de 160 → 60 | 🟠 Alto | Muy bajo |
| 7 | **Cambiar embedding a `BAAI/bge-m3`** (no es óptimo para español legal) | 🟠 Alto | Medio |
| 8 | **Usar Gemini 2.5** en lugar de 2.0-flash para generation | 🟠 Alto | Muy bajo |
| 9 | **Implementar structured output** para citations forzadas | 🟡 Medio | Medio |
| 10 | **Implementar metadata filters** en retriever | 🟡 Medio | Medio |
| 11 | **Corregir o eliminar HyDE** (hyde_passage generado pero descartado) | 🟡 Medio | Bajo |
| 12 | **Implementar MMR** para diversidad de fuentes | 🟡 Medio | Medio |
| 13 | **Parent-child chunking** para contexto completo | 🟢 Mejora | Alto |
| 14 | **Semantic chunking** en lugar de fixed-size | 🟢 Mejora | Alto |

---

## 1. Data Pipeline — Calidad de Datos Ingeridos

### 1.1 Normalización

✅ **Calidad: BUENA**

- Mínimas transformaciones: whitespace, triple→double newlines, strip non-printables
- Preserva terminología legal completamente
- Estructura Markdown intacta

### 1.2 Segmentación Legal

✅ **Calidad: BUENA — pero diferente de expectativa**

El pipeline segmenta en **8 tipos**: `metadata, facts, claims, legal_basis, evidence, analysis, decision, citations`

| Expectativa | Realidad |
|-------------|----------|
| Contexto | → `facts` |
| Desarrollo | → `legal_basis` + `evidence` (distribuido) |
| Análisis | → `analysis` |
| Decisión | → `decision` |

La estructura está bien diseñada para documentos judiciales.

### 1.3 Referencias Internas — ⚠️ PROBLEMA CRÍTICO

**`references.py:85-98` remueve sistemáticamente jurisprudencia:**

```python
# Patrones que reciben score +3 y son eliminados
r"^\s*\d{1,2}\s+(corte constitucional|consejo de estado...)"
r"^\s*\d{1,2}\s+(m\.p\.)"
```

**Lo que se pierde:**
- Citas a precedentes: `"sentencia T-1234 de 2020"` — ELIMINADO
- Referencias a Corte Constitucional, Consejo de Estado — ELIMINADO
- Blocks de jurisprudencia completos

**Lo que se preserva:**
- Referencias a artículos: `"según el artículo 45"` ✅

**Impacto en calidad**: Reducción significativa del contexto legal. Un documento que cita 10 sentencias previas pierde 8-10 de ellas antes de ser indexado. Esto afecta directamente la capacidad del RAG de retrieve precedents relevantes.

### 1.4 Footnotes

- **Preservados**: Números de footnote pegados a términos legales (`artículo14` → `artículo`) ✅
- **Removidos**: Cuerpos de footnotes con razonamiento legal ⚠️
- Los citation blocks de decisiones citadas son removidos

### 1.5 Tablas

⚠️ **Sin manejo específico**

- Docling output como `| column | column |` markdown
- No hay limpieza ni validación de contenido tabular
- Errors de OCR en tablas se propagan directamente

### 1.6 Listas Numeradas Legales

✅ **Buena calidad**

```python
# Patrones protegidos de merge
^\d{1,3}\.\s     # 1. 2.3.
^[a-z]\)\s       # a) b)
^[ivxIVX]+\.\s   # i. ii.
^\([a-z]\)\s     # (a) (b)
^(PRIMERO|SEGUNDO|...)
```

### 1.7 OCR

⚠️ **Moderada — correcciones limitadas**

Solo ~12 patrones de corrección:
```
ci6nes → uncion → ón, 0→o, l[0O]s→los, d[0O]s→dos
```

No hay spell-check contra terminología legal, no hay corrección basada en language model.

### 1.8 Citas Legales

| Tipo | Preservación |
|------|-------------|
| Referencias a artículos (`artículo 45`, `ley 1234`) | ✅ Preservadas |
| Citas a precedentes (`T-1234`, `C-456`) | ❌ Removidas |
| Jurisprudencia blocks | ❌ Removidos |

---

## 2. Chunking — Calidad de Fragmentación

### 2.1 Parámetros Actuales

| Parámetro | Valor | Evaluación |
|-----------|-------|------------|
| `chunk_size` | 1000 chars | 🟠 Pequeño para argumentos legales largos |
| `chunk_overlap` | 200 (20%) | 🟡 Puede romper dependencias transfrase |
| Separators | `["\n\n", "\n", ". ", " ", ""]` | 🔴 **PROBLEMA CRÍTICO** |

### 2.2 El Problema del Separador `.` — 🔴 CRÍTICO

```python
separators=["\n\n", "\n", ". ", " ", ""]
```

**Efectos en texto legal español:**

```
"Art. 142.3 del Código Civil" 
  → ["Art. 142", "3 del Código Civil"]  # Cita fragmentada!

"Sr. Juan Pérez"
  → ["Sr", "Juan Pérez"]  # Tratamiento corrupto

"etc."
  → ["etc", ""]  # Abreviaturas destruidas
```

Cada fragmento queda semánticamente corrupto. Un chunk que contiene `["Art. 142"` y otro con `["3 del Código Civil"]` no tienen relación semántica reconocible por el embedding.

**Mejora sugerida:**
```python
separators=["\n\n", "\n", "; ", ", ", ". ", " ", ""]
```
O al mínimo, usar `". "` en lugar de `"."` para evitar splits en medio de oraciones.

### 2.3 Coherence de Chunks (Sample Analysis)

Los samples de `data/gold/` muestran que **internamente los chunks son coherentes**:
- Paragraph-level, bien definidos
- Metadatos ricos (`section_name`, `section_heading`, `summary`, `keywords`, `entities`)
- Promedio ~708 chars, rango 1-997

**Problemas observados:**
- Algunos chunks mínimos (1 char) — no hay filtering
- Chunk 3 del ejemplo es puro "NOTIFÍQUESE Y CÚMPLASE" + signatures — sin valor para retrieval
- El `overlap=200` no es suficiente para mantener contexto entre chunks de la misma sección

### 2.4 No Parent-Child Indexing

❌ **No implementado**

Un query sobre "nulidad del contrato" puede retrieve chunks aislados sin acceso al contexto completo de la sección. Sería mejor:

1. Primero retrieve la sección completa (`Desarrollo`)
2. Luego retrieve sub-chunks relevantes

### 2.5 Semantic Chunking

❌ **No implementado**

Usa fixed-size character splitting. Semantic chunking (embeddings-based) preservaría mejor las fronteras de párrafos y argumentos legales.

---

## 3. Retrieval — Calidad de Recuperación

### 3.1 Embedding Model

```
Actual: nomic-embed-text (default)
       embeddinggemma:latest (si configurado)
Problema: Modelo general-purpose, NO optimizado para español legal colombiano
```

**Modelos superiores para español legal:**

| Modelo | Dims | Benchmark | Notas |
|--------|------|-----------|-------|
| `BAAI/bge-m3` | 1024 | MTEB leader | #1 multilingual, semantic search |
| `intfloat/multilingual-e5-large` | 1024 | MTEB | Fine-tuneable, excellent Spanish |
| `e5-mistral-7b-instruct` | 4096 | MTEB | Mejor calidad, más lento |

### 3.2 Parámetros de Retrieval — Problemas

| Parámetro | Actual | Recomendado | Severidad |
|-----------|--------|-------------|-----------|
| `DEFAULT_K` | 3 | 5-8 | 🔴 Muy bajo para contexto legal |
| `K_CANDIDATES` | 10 | 15-20 | Solo se usa con reranker |
| `RRF c` | 160 | 60 | 🔴 Flattens rankings demasiado |
| Weights BM25/Vector | 0.3/0.7 | 0.3/0.7 | ✅ Razonable |

**`RRF c=160`**: El estándar es ~60. Un c alto reduce drásticamente el beneficio de fusionar rankings.文献 sugiere c=60.

### 3.3 k Inconsistente

| Ubicación | k |
|-----------|---|
| `config.py` | `DEFAULT_K=4` |
| `retriever.py` (todos los retrievers) | `k=3` |

El retriever siempre usa `k=3`, ignorando `DEFAULT_K=4` de config.

### 3.4 Metadata Filters

❌ **No disponibles en retrieval**

Los metadatos se almacenan (`source`, `keywords_str`, etc.) pero `HybridEnsembleRetriever` no tiene parámetro `filter`. No se puede filtrar por:
- Tribunal (Tribunal Administrativo del Magdalena, etc.)
- Año de la decisión
- Tipo de caso (acción popular, nulidad, etc.)
- Parte involucrada

### 3.5 MMR — No Implementado

❌ **Sin diversidad de fuentes**

Múltiples chunks del mismo documento dominan los resultados. Para queries que requieren diversidad de jurisprudencia, esto es un problema.

### 3.6 HyDE — Código Muerto

```python
# query_enricher.py: enriquecimiento genera:
{
  "expanded_query": "...",   # ✅ USADO en retrieval
  "legal_concepts": [...],   # ✅ USADO en retrieval
  "sub_questions": [...],    # ✅ USADO en retrieval
  "hyde_passage": "..."      # ❌ GENERADO PERO DESCARTADO
}
```

`hyde_passage` se genera vía LLM pero **nunca llega al retriever**. Solo `expanded_query` se usa. Esto es:
1. Un gasto de latencia innecesario (LLM call adicional)
2. Una feature incompleta

**Opciones**: 
- Implementar HyDE correctamente (usar `hyde_passage` para retrieve)
- Deshabilitar HyDE y eliminar el código muerto

### 3.7 Reranker

- `OllamaReranker` existe pero `use_reranker=False` en demo
- `num_ctx=1024` trunca documentos legales largos
- `num_predict=16` muy bajo para scoring output

---

## 4. Generation — Calidad de Generación

### 4.1 Modelo

```
gemini-2.0-flash (default)
```

**Problema**: Flash es optimizado para velocidad. Para **rigor legal**, un modelo de razonamiento es preferible:
- `gemini-2.5-flash` — mejor reasoning
- `gemini-2.5-pro` — máximo quality

### 4.2 `_clean_answer` — 🔴 CRÍTICO

```python
# main.py:66-74
def _clean_answer(text: str) -> str:
    # Remueve patrones como (doc1), [doc2], footnote markers
    # DESTRUYE la trazabilidad de citations!!!
```

**Esto es un problema serio de calidad legal.** El usuario no puede verificar qué documento respaldó la respuesta. En un sistema legal, las citations son esenciales para confianza y verificabilidad.

**Recomendación**: Eliminar `_clean_answer` o hacerlo opcional.

### 4.3 Prompt Engineering

**Fortalezas:**
- Reglas de fidelidad al contexto bien diseñadas
- Checklist de auto-revisión comprehensivo
- Fallback para evidencia insuficiente

**Debilidades:**
- No hay constraint duro "ONLY use provided context" — es implícito, no enforced
- No hay máximo de tokens para el bloque de contexto
- Sin structured output — citations son texto libre, pueden ser hallucinados

### 4.4 Structured Output

❌ **No usado**

`StrOutputParser` permite free-form text. Para citations forzadas, un schema Pydantic con campo `citations: list[str]` + modo JSON de Gemini sería más confiable.

### 4.5 Context Window Management

⚠️ **Sin límite**

`k_candidates=10` puede producir un bloque de contexto muy largo. Sin truncation, el modelo puede tener problemas de atención o truncamiento.

---

## 5. Evaluation — Calidad de Evaluación

### 5.1 El Dataset de Evaluación — 🔴 CRÍTICO

```python
TEST_ITEMS = [
    {"question": "¿Cómo se llamaba el gato del cuento 'El gato negro'?"},
    {"question": "¿Dónde se posó el cuervo en el cuento 'El cuervo'?"},
    {"question": "¿Qué relación tenía Leonora con el narrador?"},
    {"question": "¿Qué órgano del cuerpo es central en 'El corazón delator'?"},
]
```

**Son cuentos de Edgar Allan Poe.** El dataset NO representa el dominio legal colombiano.

La evaluación RAGAS resultante es **completamente irrelevante** para el sistema.

### 5.2 Métricas RAGAS

✅ **Configuradas correctamente:**
- `context_precision`
- `context_recall`
- `faithfulness`
- `answer_relevancy`

### 5.3 Recomendación

Crear dataset con **20-50 preguntas reales** de abogados sobre temas como:
- deslinde_amojonamiento
- concesión/permiso de playa
- acceso público a la costa
- sanción administrativa
- licencia ambiental
- dominio público marítimo-terrestre

Con ground truth: documentos relevantes + answer expected.

---

## 6. Resumen de Problemas de Calidad

| Área | #1 Problema | Severidad |
|------|-------------|-----------|
| **Data Ingestion** | Pérdida de citas jurisprudenciales (`sentencia T-1234`) | 🔴 Crítico |
| **Chunking** | Separador `.` fragmenta citas legales (`Art. 142.3`) | 🔴 Crítico |
| **Generation** | `_clean_answer` destruye citations | 🔴 Crítico |
| **Evaluation** | Ground truth de Poe — no representa el dominio | 🔴 Crítico |
| **Retrieval** | `k=3` muy bajo, `RRF c=160` flatten demasiado | 🟠 Alto |
| **Embeddings** | `nomic-embed-text` no óptimo para español legal | 🟠 Alto |
| **Generation** | `gemini-2.0-flash` no ideal para rigor legal | 🟠 Alto |
| **Retrieval** | No metadata filters, no MMR | 🟠 Alto |
| **HyDE** | Código muerto — `hyde_passage` generado pero descartado | 🟠 Alto |
| **Retrieval** | k inconsistente (config=4, retriever=3) | 🟡 Medio |
| **Generation** | Sin structured output | 🟡 Medio |
| **Chunking** | `chunk_size=1000` pequeño | 🟡 Medio |
| **Chunking** | No parent-child indexing | 🟡 Medio |
| **Data** | No manejo de tablas | 🟡 Medio |

---

## 7. Roadmap de Mejoras

### Inmediato (high impact, low effort)

1. **Cambiar separador `.` → `. "`** en `splitter_and_enrich.py`
2. **Eliminar `remove_internal_references()`** o excluir jurisprudencia del removal en `references.py`
3. **Eliminar `_clean_answer`** o hacer optional en `main.py`
4. **Crear dataset de evaluación real** con preguntas de sentencias colombianas

### Corto plazo (high impact, medium effort)

5. **Aumentar `DEFAULT_K`** de 3 → 5-8 en `retriever.py`
6. **Bajar `RRF c`** de 160 → 60 en `retriever.py`
7. **Cambiar embedding model** a `BAAI/bge-m3` (y cambiar dimensión a 1024)
8. **Usar Gemini 2.5-flash** en lugar de 2.0-flash para generation
9. **Implementar structured output** con Pydantic schema para citations forzadas
10. **Implementar metadata filters** en `HybridEnsembleRetriever`
11. **Corregir o eliminar HyDE** — si se usa, que `hyde_passage` vaya al retriever; si no, deshabilitar

### Medio plazo (quality improvements)

12. **Parent-child chunking** para contexto completo de secciones
13. **Semantic chunking** basado en embeddings
14. **Implementar MMR** para diversidad de fuentes en retrieval
15. **Filtrar chunks vacíos** durante ingestión (tamaño mínimo, ej. 50 chars)
16. **Manejo de tablas** específicas para markdown tables
17. **Async parallelization** del enrichment para mayor throughput (no calidad pero permite más experimentation)

---

## 8. Notas sobre la Arquitectura

### Lo que está bien

- **Híbrido BM25 + Vector + RRF**: excelente para combinar keyword + semantic search
- **4-section split**: buena estructura para documentos judiciales
- **Enriquecimiento con Gemini**: summaries, keywords, entities son útililes para retrieval
- **Lifespan pre-warming**: evita cold-start en API
- **SSE streaming**: buena experiencia de usuario

### Lo que necesita atención

- **Separador de chunking** — es la bug más simple con mayor impacto
- **Citations** — esenciales para un sistema legal
- **Embeddings** — el modelo hace toda la diferencia en retrieval quality
- **Evaluación** — sin ground truth del dominio, no hay forma de medir mejora
