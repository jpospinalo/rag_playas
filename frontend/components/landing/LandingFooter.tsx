export function LandingFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-6 text-xs text-muted">
        <span>
          <span
            className="font-[family-name:var(--font-display)] font-semibold"
            translate="no"
          >
            RAG PLAYAS
          </span>{" "}
          &copy; {new Date().getFullYear()}
        </span>
        <span>Jurisprudencia marítima y costera · Colombia</span>
      </div>
    </footer>
  );
}
