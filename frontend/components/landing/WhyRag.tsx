export function WhyRag() {
  return (
    <section
      className="mx-auto w-full max-w-5xl px-6 py-20"
      aria-labelledby="why-rag-heading"
    >
      <div className="max-w-2xl">
        <h2
          id="why-rag-heading"
          className="font-[family-name:var(--font-display)] text-balance mb-6 text-3xl font-semibold leading-snug text-foreground"
        >
          Por qué RAG es la tecnología idónea para el derecho.
        </h2>
        <p className="mb-4 text-base leading-relaxed text-muted">
          Los modelos de lenguaje generativo pueden «alucinar» —fabricar
          referencias inexistentes o distorsionar hechos—, un riesgo
          inaceptable en el ámbito jurídico. La arquitectura RAG elimina ese
          riesgo al vincular cada respuesta a fragmentos reales del corpus: si
          la información no está en la base documental, el sistema lo indica.
        </p>
        <p className="text-base leading-relaxed text-muted">
          El resultado es un asistente que actúa como un colaborador que ha
          leído toda la jurisprudencia disponible y cita sus fuentes con
          precisión, liberando al profesional para centrarse en el análisis y
          la estrategia.
        </p>
      </div>
    </section>
  );
}
