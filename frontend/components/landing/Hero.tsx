import Link from "next/link";

export function Hero() {
  return (
    <section className="mx-auto w-full max-w-5xl px-6 pb-24 pt-20 md:pt-32">
      <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-accent">
        Jurisprudencia · Derecho Marítimo · Costas
      </p>
      <h1 className="font-[family-name:var(--font-display)] text-balance mb-6 text-5xl font-semibold leading-tight tracking-tight text-foreground md:text-6xl lg:text-7xl">
        La jurisprudencia costera
        <br className="hidden md:block" />
        <span className="text-accent"> al alcance de su consulta.</span>
      </h1>
      <p className="mb-10 max-w-2xl text-pretty text-lg leading-relaxed text-muted">
        Acceda a jurisprudencia colombiana sobre playas, bienes de uso público
        costero y derecho marítimo. Respuestas fundamentadas en fuentes
        verificadas, sin búsquedas manuales, sin ambigüedad.
      </p>
      <Link
        href="/chat"
        className="inline-flex items-center gap-2 rounded-md bg-navy px-6 py-3 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
      >
        Consultar jurisprudencia
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M5 12h14" />
          <path d="m12 5 7 7-7 7" />
        </svg>
      </Link>
    </section>
  );
}
