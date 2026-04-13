import Link from "next/link";

export function ChatHeader() {
  return (
    <header className="shrink-0 border-b border-border bg-surface/95 backdrop-blur-sm">
      <div className="mx-auto grid max-w-3xl grid-cols-[1fr_auto_1fr] items-center px-4 py-3">
        <Link
          href="/"
          aria-label="Volver a la página principal"
          className="-ml-1 flex w-fit items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="m15 18-6-6 6-6" />
          </svg>
          Inicio
        </Link>

        <span
          className="font-[family-name:var(--font-display)] text-center text-sm font-semibold uppercase tracking-widest text-foreground"
          translate="no"
        >
          RAG <span className="text-accent">PLAYAS</span>
        </span>

        {/* Balance spacer */}
        <div aria-hidden="true" />
      </div>
    </header>
  );
}
