const STEPS = [
  {
    number: "1",
    title: "Recuperación",
    description:
      "Ante su consulta, el sistema realiza una búsqueda híbrida —léxica BM25 y semántica vectorial— sobre el corpus de jurisprudencia, identificando los fragmentos más relevantes.",
  },
  {
    number: "2",
    title: "Aumentación",
    description:
      "Solo los fragmentos verificados del corpus legal se incorporan como contexto al modelo. El modelo no puede ir más allá de las fuentes recuperadas.",
  },
  {
    number: "3",
    title: "Generación",
    description:
      "El modelo redacta una respuesta en lenguaje jurídico natural, siempre con referencia explícita a los documentos fuente utilizados.",
  },
] as const;

export function HowItWorks() {
  return (
    <section
      className="mx-auto w-full max-w-5xl px-6 py-20"
      aria-labelledby="how-it-works-heading"
    >
      <h2
        id="how-it-works-heading"
        className="text-balance mb-3 text-xs font-semibold uppercase tracking-widest text-accent"
      >
        Cómo funciona
      </h2>
      <p className="font-[family-name:var(--font-display)] mb-12 max-w-xl text-pretty text-3xl font-semibold leading-snug text-foreground">
        Arquitectura RAG: respuestas ancladas en documentos reales.
      </p>

      <ol className="grid gap-8 md:grid-cols-3" role="list">
        {STEPS.map((step) => (
          <li key={step.number} className="flex flex-col gap-3">
            <div
              className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-surface text-sm font-semibold tabular-nums text-accent"
              aria-hidden="true"
            >
              {step.number}
            </div>
            <h3 className="font-[family-name:var(--font-display)] text-balance text-lg font-semibold text-foreground">
              {step.title}
            </h3>
            <p className="text-sm leading-relaxed text-muted">
              {step.description}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
