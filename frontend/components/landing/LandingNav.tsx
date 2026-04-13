import Link from "next/link";

export function LandingNav() {
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-surface/90 backdrop-blur-sm">
      <nav
        className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4"
        aria-label="Navegación principal"
      >
        <span
          className="font-[family-name:var(--font-display)] text-base font-semibold uppercase tracking-widest text-foreground"
          translate="no"
        >
          RAG <span className="text-accent">PLAYAS</span>
        </span>
        <Link
          href="/chat"
          className="rounded-md border border-accent px-4 py-1.5 text-sm font-medium text-accent transition-colors duration-150 hover:bg-accent hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
        >
          Iniciar consulta
        </Link>
      </nav>
    </header>
  );
}
