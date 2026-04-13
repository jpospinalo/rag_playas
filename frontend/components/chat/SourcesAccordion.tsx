"use client";

import { useRef, useState } from "react";
import type { SourceDocument } from "@/lib/types";

interface SourcesAccordionProps {
  sources: SourceDocument[];
}

export function SourcesAccordion({ sources }: SourcesAccordionProps) {
  const [open, setOpen] = useState(false);
  const contentId = useRef(
    `sources-${Math.random().toString(36).slice(2)}`
  ).current;

  if (sources.length === 0) return null;

  return (
    <div className="mt-4 border-t border-border pt-3">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded text-xs text-muted transition-colors duration-150 hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1"
      >
        <span className="flex items-center gap-1.5 font-medium">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="11"
            height="11"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
          {sources.length}{" "}
          {sources.length === 1 ? "fuente consultada" : "fuentes consultadas"}
        </span>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className="shrink-0 transition-transform duration-300 ease-in-out"
          style={{
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transformBox: "fill-box",
            transformOrigin: "center",
          }}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {/* CSS grid trick — animates height without JS measurement */}
      <div
        id={contentId}
        aria-hidden={!open}
        className="grid overflow-hidden"
        style={{
          gridTemplateRows: open ? "1fr" : "0fr",
          transitionProperty: "grid-template-rows",
          transitionDuration: "300ms",
          transitionTimingFunction: "cubic-bezier(0.4, 0, 0.2, 1)",
        }}
      >
        <div className="overflow-hidden">
          <ul className="mt-3 flex flex-col gap-2" role="list">
            {sources.map((src, i) => (
              <li
                key={i}
                className="rounded-xl border border-border bg-background/60 p-3"
              >
                {src.title && (
                  <p
                    className="mb-1 truncate text-xs font-semibold text-foreground"
                    translate="no"
                  >
                    {src.title}
                  </p>
                )}
                <p className="line-clamp-3 text-xs leading-relaxed text-muted">
                  {src.content}
                </p>
                {src.source && (
                  <p
                    className="mt-1.5 truncate font-[family-name:var(--font-mono,monospace)] text-[10px] text-muted/60"
                    translate="no"
                  >
                    {src.source}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
