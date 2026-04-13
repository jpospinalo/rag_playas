"use client";

import { useEffect } from "react";

interface ChatInputProps {
  value: string;
  loading: boolean;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export function ChatInput({
  value,
  loading,
  textareaRef,
  onChange,
  onSubmit,
}: ChatInputProps) {
  /* Auto-resize: runs both on user typing and on programmatic value changes */
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [value, textareaRef]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  }

  return (
    <div className="shrink-0 border-t border-border bg-surface/95 backdrop-blur-sm">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="mx-auto flex max-w-3xl items-end gap-2.5 px-4 py-3"
        aria-label="Formulario de consulta"
      >
        <label htmlFor="chat-input" className="sr-only">
          Escriba su consulta jurídica
        </label>
        <textarea
          ref={textareaRef}
          id="chat-input"
          name="question"
          rows={1}
          placeholder="Escriba su consulta…"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          autoComplete="off"
          spellCheck
          disabled={loading}
          className="min-w-0 flex-1 resize-none rounded-xl border border-border bg-background px-4 py-3 text-sm leading-6 text-foreground placeholder:text-muted/70 transition-[border-color,box-shadow] duration-150 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/20 disabled:opacity-50"
          style={{ overflowY: "hidden" }}
        />
        <button
          type="submit"
          disabled={loading || !value.trim()}
          aria-label={loading ? "Consultando…" : "Enviar consulta"}
          className="flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-xl bg-navy text-white transition-[background-color,opacity] duration-150 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-35"
        >
          {loading ? (
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
              className="animate-spin"
            >
              <path d="M21 12a9 9 0 1 1-6.219-8.56" />
            </svg>
          ) : (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="m22 2-7 20-4-9-9-4Z" />
              <path d="M22 2 11 13" />
            </svg>
          )}
        </button>
      </form>
      <p className="pb-3 text-center text-[10px] text-muted/50">
        Respuestas basadas en el corpus indexado · Shift + Enter para nueva
        línea
      </p>
    </div>
  );
}
