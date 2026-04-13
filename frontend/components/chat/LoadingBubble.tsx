import { TypingDots } from "@/components/chat/TypingDots";

export function LoadingBubble() {
  return (
    <div className="flex justify-start animate-message-in">
      <div
        className="rounded-2xl rounded-tl-sm bg-surface px-5 py-4 shadow-sm"
        style={{
          border: "1px solid var(--border)",
          borderLeftColor: "var(--accent)",
          borderLeftWidth: "2px",
        }}
      >
        <TypingDots />
        <span className="sr-only">Consultando jurisprudencia…</span>
      </div>
    </div>
  );
}
