# evaluation/ragas_eval.py

# TODO: Cambiar a playas (actualmente poe)

from __future__ import annotations

import json
import os
import warnings
from typing import Any

from datasets import Dataset
from langchain_ollama import ChatOllama, OllamaEmbeddings
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
)
from ragas.run_config import RunConfig

from rag.core.generator import generate_answer

warnings.filterwarnings("ignore", category=FutureWarning)


# ============================================================
#  1. Ítems de prueba
# ============================================================

"""
TEST_ITEMS: List[Dict[str, str]] = [
    {
        "question": "¿Cómo se llamaba el gato del cuento 'El gato negro'?",
        "ground_truth": "El gato del narrador se llamaba Plutón.",
    },
    {
        "question": "¿Dónde se posó el cuervo en el cuento 'El cuervo'?",
        "ground_truth": "El cuervo se posó sobre un busto de Minerva o Palas, sobre la puerta.",
    },
    {
        "question": "¿Qué relación tenía Leonora con el narrador en 'El cuervo'?",
        "ground_truth": "Leonora era la amada del narrador, cuya muerte le causó profunda desventura.",
    },
    {
        "question": "¿Qué órgano del cuerpo es central en el cuento 'El corazón delator'?",
        "ground_truth": "El órgano central del cuento es el corazón del anciano.",
    },
]
"""

TEST_ITEMS: list[dict[str, str]] = [
    {
        "question": "¿Cómo se llamaba el gato del cuento 'El gato negro'?",
        "ground_truth": "El gato del narrador se llamaba Plutón.",
    },
]


# ============================================================
#  2. Construir dataset a partir de tu RAG
# ============================================================

MAX_CONTEXT_DOCS = 2  # solo 2 chunks por pregunta para pruebas rápidas


def build_eval_dataset() -> tuple[Dataset, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []

    for item in TEST_ITEMS:
        question = item["question"]
        gt = item["ground_truth"]

        answer, docs = generate_answer(question)
        answer = answer or ""  # defensa por si generate_answer devuelve None

        # Limitar la cantidad de docs enviados a RAGAS
        docs = docs or []
        docs = docs[:MAX_CONTEXT_DOCS]

        contexts = [d.page_content for d in docs]

        rows.append(
            {
                "question": question,
                "answer": answer,
                "contexts": contexts,
                "ground_truth": gt,
            }
        )

    dataset = Dataset.from_list(rows)
    return dataset, rows


# ============================================================
#  3. Juez en Ollama con limpieza estricta de JSON
# ============================================================


class JsonStrictOllama(ChatOllama):
    """
    Variante de ChatOllama pensada para RAGAS.

    Objetivo:
    - Limpiar fences markdown y texto basura alrededor del JSON.
    - Extraer el primer bloque JSON válido si hay ruido.
    - Normalizar SOLO tipos de campos clave que RAGAS espera:
        * verdict        -> 0/1
        * Attributed     -> bool
        * noncommittal   -> bool
        * question       -> str
    - No cambiar la estructura ni los nombres de las claves.
      Esto permite que funcione con:
        - context_precision
        - context_recall
        - faithfulness
        - answer_relevancy
    """

    # ---------- utilidades internas de limpieza ----------

    @staticmethod
    def _strip_json_fences(text: str) -> str:
        """
        Elimina fences Markdown ```...``` de la salida.
        """
        s = text.strip()
        if s.startswith("```"):
            lines = s.splitlines()
            # quitar la primera línea ``` o ```json, etc.
            lines = lines[1:]
            # quitar la última línea si es ```
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            s = "\n".join(lines).strip()
        return s

    @staticmethod
    def _extract_json_block(text: str) -> str:
        """
        Si el texto contiene un JSON embebido (p.ej. texto antes/después),
        intenta extraer el primer bloque bien formado entre '{' y '}'.
        Si no lo consigue, devuelve el texto original.
        """
        s = text.strip()
        start = s.find("{")
        end = s.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return s
        candidate = s[start : end + 1]
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            return s

    @staticmethod
    def _normalize_verdict(raw: Any) -> int:
        """
        Normaliza cualquier valor a 0 o 1.

        Regla: values >= 0.5 -> 1, sino 0.
        (Soporta bool, str numérica, int, float).
        """
        if isinstance(raw, bool):
            return 1 if raw else 0

        try:
            val = float(raw)
        except Exception:
            return 0
        return 1 if val >= 0.5 else 0

    @staticmethod
    def _normalize_bool(raw: Any) -> bool:
        """
        Normaliza un valor a bool.
        """
        if isinstance(raw, bool):
            return raw
        try:
            # acepta 0/1, "0"/"1", etc.
            return bool(float(raw))
        except Exception:
            # si no sabemos qué es, ser conservadores
            return False

    @classmethod
    def _coerce_types_for_ragas(cls, data: Any) -> Any:
        """
        Recorre recursivamente el JSON y corrige solo tipos de campos
        relevantes para RAGAS, sin cambiar la estructura.
        """
        if isinstance(data, dict):
            new: dict[str, Any] = {}
            for k, v in data.items():
                if k == "verdict":
                    new[k] = cls._normalize_verdict(v)
                elif k == "Attributed":
                    new[k] = cls._normalize_bool(v)
                elif k == "noncommittal":
                    new[k] = cls._normalize_bool(v)
                elif k == "question":
                    # answer_relevancy: asegura que sea string
                    new[k] = "" if v is None else str(v)
                else:
                    new[k] = cls._coerce_types_for_ragas(v)
            return new
        elif isinstance(data, list):
            return [cls._coerce_types_for_ragas(x) for x in data]
        else:
            return data

    @classmethod
    def _normalize_json(cls, text: str) -> str:
        """
        Normaliza la salida de texto del modelo a un JSON limpio sin
        alterar el esquema.

        Pasos:
        - Quita fences.
        - Intenta extraer el bloque JSON principal.
        - Si parsea:
            * Corrige tipos de campos clave (verdict, Attributed, noncommittal, question)
            * Devuelve json.dumps(data)
        - Si NO parsea:
            * Devuelve el texto tal cual (RAGAS mostrará warning, igual que sin wrapper).
        """
        s = text.strip()
        if not s:
            # cadena vacía, que RAGAS tratará como inválida si esperaba JSON
            return s

        s_candidate = cls._extract_json_block(s)

        try:
            data = json.loads(s_candidate)
        except Exception:
            # No se pudo parsear como JSON. Devolver la mejor aproximación.
            return s_candidate

        data = cls._coerce_types_for_ragas(data)
        return json.dumps(data, ensure_ascii=False)

    # ---------- postprocesado de la respuesta de LangChain ----------

    def _postprocess_result(self, result):
        """
        Ajusta in-place result.generations para que tanto:
          - gen.message.content
          - gen.text

        contengan un string JSON limpio cuando el modelo haya generado JSON.
        """
        gens = getattr(result, "generations", [])

        # Aplanar posibles listas anidadas: List[List[Generation]] o List[Generation]
        flat_gens = []
        for item in gens:
            if isinstance(item, list):
                flat_gens.extend(item)
            else:
                flat_gens.append(item)

        for gen in flat_gens:
            # 1) message.content
            msg = getattr(gen, "message", None)
            if msg is not None:
                content = getattr(msg, "content", None)
                if isinstance(content, str):
                    cleaned = self._strip_json_fences(content)
                    cleaned = self._normalize_json(cleaned)
                    msg.content = cleaned

            # 2) gen.text
            text = getattr(gen, "text", None)
            if isinstance(text, str):
                cleaned_text = self._strip_json_fences(text)
                cleaned_text = self._normalize_json(cleaned_text)
                gen.text = cleaned_text

        return result

    # ---------- hooks internos de ChatOllama ----------

    def _generate(self, messages, stop=None, **kwargs):
        # Forzar que NO use streaming aunque RAGAS/LangChain lo pida
        kwargs.pop("stream", None)
        res = super()._generate(messages, stop=stop, stream=False, **kwargs)
        return self._postprocess_result(res)

    async def _agenerate(self, messages, stop=None, **kwargs):
        # Igual en la versión async
        kwargs.pop("stream", None)
        res = await super()._agenerate(messages, stop=stop, stream=False, **kwargs)
        return self._postprocess_result(res)


def get_ragas_models():
    """
    Modelos para RAGAS:

    - LLM juez: Mistral (u otro modelo) servido por Ollama en un endpoint
      accesible vía ngrok (por defecto: https://98d22ba5053f.ngrok-free.app).
      Se puede cambiar con la variable de entorno OLLAMA_EVAL_BASE_URL
      y el nombre de modelo con OLLAMA_EVAL_MODEL.

    - Embeddings: embeddinggemma en Ollama local (por defecto http://localhost:11434),
      modificable con OLLAMA_EMBED_BASE_URL y OLLAMA_EMBED_MODEL.
    """
    judge_base_url = os.getenv("OLLAMA_EVAL_BASE_URL")

    judge_model_name = os.getenv("OLLAMA_EVAL_MODEL")

    embed_base_url = os.getenv("OLLAMA_EMBED_BASE_URL")
    embed_model_name = os.getenv("OLLAMA_EMBED_MODEL")

    llm_judge = JsonStrictOllama(
        model=judge_model_name,
        base_url=judge_base_url,
        temperature=0.0,
        num_ctx=2048,
        num_predict=256,
        format="json",
        keep_alive=60,  # o elimina el parámetro para usar el default
    )

    embeddings = OllamaEmbeddings(
        model=embed_model_name,
        base_url=embed_base_url,
    )

    return llm_judge, embeddings


# ============================================================
#  4. Ejecutar evaluación RAGAS (por ahora solo context_precision)
# ============================================================


def run_ragas_evaluation(dataset: Dataset) -> dict[str, Any]:
    """
    Ejecuta RAGAS sobre el dataset dado usando:

        - context_precision (por ahora)
        - LLM juez y embeddings de get_ragas_models()
    """
    llm_judge, embeddings = get_ragas_models()

    metrics = [
        # context_precision,
        # context_recall,
        # faithfulness,
        answer_relevancy,
    ]

    for m in metrics:
        m.llm = llm_judge
        m.embeddings = embeddings

    run_config = RunConfig(
        timeout=600,
        max_workers=1,
    )

    print("\n=== Ejecutando métricas RAGAS ===")

    res = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=llm_judge,
        embeddings=embeddings,
        raise_exceptions=True,
        run_config=run_config,
    )

    df = res.to_pandas()
    all_results: dict[str, Any] = {}

    for m in metrics:
        name = m.name
        if name not in df.columns:
            continue
        series = df[name]
        valid_values = [float(v) for v in series.tolist() if v == v]  # filtra NaN
        all_results[name] = {
            "per_sample": valid_values,
            "mean": float(sum(valid_values) / len(valid_values)) if valid_values else float("nan"),
        }

    return all_results


# ============================================================
#  5. Guardar JSONs y punto de entrada
# ============================================================


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def main(
    dataset_json_path: str = "evaluation/ragas_eval_dataset.json",
    summary_json_path: str = "evaluation/ragas_eval_summary.json",
) -> None:
    dataset, rows = build_eval_dataset()

    _ensure_parent_dir(dataset_json_path)
    _ensure_parent_dir(summary_json_path)

    with open(dataset_json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    results = run_ragas_evaluation(dataset)

    metrics_summary: dict[str, Any] = {
        "n_samples": len(rows),
        "metrics": {name: vals["mean"] for name, vals in results.items()},
    }

    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(metrics_summary, f, ensure_ascii=False, indent=2)

    print(f"\nDataset de evaluación guardado en: {dataset_json_path}")
    print(f"Resumen de métricas guardado en:  {summary_json_path}")
    print("Resumen:", metrics_summary)


if __name__ == "__main__":
    main()
