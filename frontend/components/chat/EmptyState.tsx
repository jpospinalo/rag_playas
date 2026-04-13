const EXAMPLE_QUESTIONS = [
  "¿Cuál es el régimen jurídico de las playas en Colombia?",
  "¿Qué regula la Ley 99 de 1993 en materia de zonas costeras?",
  "¿Cómo se tramita una concesión sobre bienes de uso público costero?",
] as const;

interface EmptyStateProps {
  onSelectExample: (question: string) => void;
}

export function EmptyState({ onSelectExample }: EmptyStateProps) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-16 text-center animate-fade-in">
      <div
        className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl border border-border bg-surface shadow-sm"
        aria-hidden="true"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-accent"
        >
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </div>

      <h2 className="font-[family-name:var(--font-display)] mb-2 text-xl font-semibold text-foreground">
        Asistente de Jurisprudencia Costera
      </h2>
      <p className="mb-8 max-w-xs text-sm leading-relaxed text-muted">
        Sus consultas se responden con base exclusiva en el corpus de
        jurisprudencia colombiana indexado.
      </p>

      <ul
        className="flex w-full max-w-sm flex-col gap-2"
        role="list"
        aria-label="Consultas de ejemplo"
      >
        {EXAMPLE_QUESTIONS.map((q) => (
          <li key={q}>
            <button
              type="button"
              onClick={() => onSelectExample(q)}
              className="w-full rounded-xl border border-border bg-surface px-4 py-3 text-left text-sm leading-snug text-muted transition-colors duration-150 hover:border-accent/50 hover:bg-accent-light hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
            >
              {q}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
