# evaluation/ragas_eval_gemmini.py

# TODO: Cambiar a playas (actualmente poe)

from __future__ import annotations

import asyncio
import json
import os
import time
import warnings
from typing import Any, ClassVar

from datasets import Dataset
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import OllamaEmbeddings
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
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
]
"""

TEST_ITEMS: list[dict[str, str]] = [
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


# ============================================================
#  2. Construir dataset a partir de tu RAG
# ============================================================

MAX_CONTEXT_DOCS = 3  # solo 2 chunks por pregunta para ahorrar tokens


def build_eval_dataset() -> tuple[Dataset, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []

    for item in TEST_ITEMS:
        question = item["question"]
        gt = item["ground_truth"]

        answer, docs = generate_answer(question)
        answer = answer or ""

        docs = (docs or [])[:MAX_CONTEXT_DOCS]
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
#  3. LLM evaluador: Gemini con rate limit y limpieza JSON
# ============================================================


class RateLimitedGemini(ChatGoogleGenerativeAI):
    """
    Wrapper sobre ChatGoogleGenerativeAI para usarlo como juez en RAGAS:

    - Aplica un delay entre llamadas para no acercarse al límite de QPM.
    - Limpia fences ```json ... ``` de la salida.
    - Intenta dejar un bloque JSON limpio.
    - Si tras limpiar la salida queda vacía, devuelve un JSON neutro
      válido para la métrica de faithfulness (NLIStatementOutput).
    """

    RATE_LIMIT_SECONDS: ClassVar[float] = float(os.getenv("RAGAS_LLM_DELAY", "9.0"))

    # ---------- utilidades de limpieza ----------

    @staticmethod
    def _strip_json_fences(text: str) -> str:
        s = text.strip()
        if s.startswith("```"):
            lines = s.splitlines()
            # quitar primera línea ``` o ```json
            lines = lines[1:]
            # quitar última línea si es ```
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            s = "\n".join(lines).strip()
        return s

    @staticmethod
    def _extract_json_block(text: str) -> str:
        """
        Si el texto contiene texto adicional + JSON, intenta extraer
        solo el primer bloque bien formado entre '{' y '}'.
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

    @classmethod
    def _clean_text(cls, text: str) -> str:
        if not isinstance(text, str):
            return text

        original = text
        s = cls._strip_json_fences(original)
        s = cls._extract_json_block(s)

        # Si después de limpiar nos quedamos sin nada, devolvemos
        # un JSON neutro compatible con NLIStatementOutput
        # (para faithfulness): {"verdicts": []}
        if not s.strip():
            return json.dumps({"verdicts": []}, ensure_ascii=False)

        return s

    def _postprocess_result(self, result):
        gens = getattr(result, "generations", [])

        flat: list[Any] = []
        for item in gens:
            if isinstance(item, list):
                flat.extend(item)
            else:
                flat.append(item)

        for gen in flat:
            # gen.text
            if hasattr(gen, "text") and isinstance(gen.text, str):
                gen.text = self._clean_text(gen.text)

            # gen.message.content (por si RAGAS usa esto)
            msg = getattr(gen, "message", None)
            if msg is not None:
                content = getattr(msg, "content", None)
                if isinstance(content, str):
                    msg.content = self._clean_text(content)

        return result

    # ---------- hooks internos de ChatGoogleGenerativeAI ----------

    def _generate(self, messages, stop=None, **kwargs):
        delay = getattr(self, "RATE_LIMIT_SECONDS", 7.0)
        if delay > 0:
            time.sleep(delay)

        kwargs.pop("stream", None)
        res = super()._generate(messages, stop=stop, **kwargs)
        return self._postprocess_result(res)

    async def _agenerate(self, messages, stop=None, **kwargs):
        delay = getattr(self, "RATE_LIMIT_SECONDS", 7.0)
        if delay > 0:
            await asyncio.sleep(delay)

        kwargs.pop("stream", None)
        res = await super()._agenerate(messages, stop=stop, **kwargs)
        return self._postprocess_result(res)


def get_ragas_models():
    """
    - LLM evaluador: Gemini (solo para RAGAS).
    - Embeddings: Ollama (ya configurados en tus variables de entorno).
    """
    gemini_model = os.getenv("GEMINI_MODEL", "gemma-3-27b-it")
    google_api_key = os.getenv("GOOGLE_API_KEY2")

    llm_judge = RateLimitedGemini(
        model=gemini_model,
        api_key=google_api_key,
        temperature=0.0,
        max_output_tokens=4098,
    )

    embed_base_url = os.getenv("OLLAMA_EMBED_BASE_URL", "http://localhost:11434")
    embed_model_name = os.getenv("OLLAMA_EMBED_MODEL", "embeddinggemma:latest")

    embeddings = OllamaEmbeddings(
        model=embed_model_name,
        base_url=embed_base_url,
    )

    return llm_judge, embeddings


# ============================================================
#  4. Ejecutar evaluación RAGAS (4 métricas)
# ============================================================


def run_ragas_evaluation(dataset: Dataset) -> dict[str, Any]:
    llm_judge, embeddings = get_ragas_models()

    metrics = [
        context_precision,
        context_recall,
        faithfulness,
        answer_relevancy,
    ]

    for m in metrics:
        m.llm = llm_judge
        m.embeddings = embeddings

    run_config = RunConfig(
        timeout=600,
        max_workers=1,  # secuencial para cuidar el rate limit
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
