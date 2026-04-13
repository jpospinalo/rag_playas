import type { SourceDocument } from "@/lib/types";
import { SourcesAccordion } from "@/components/chat/SourcesAccordion";

interface AssistantBubbleProps {
  text: string;
  sources: SourceDocument[];
}

export function AssistantBubble({ text, sources }: AssistantBubbleProps) {
  return (
    <div className="flex justify-start animate-message-in">
      <div
        className="max-w-[88%] min-w-0 break-words rounded-2xl rounded-tl-sm bg-surface px-5 py-4 text-sm leading-relaxed text-foreground shadow-sm"
        style={{
          border: "1px solid var(--border)",
          borderLeftColor: "var(--accent)",
          borderLeftWidth: "2px",
        }}
      >
        <p className="whitespace-pre-wrap">{text}</p>
        <SourcesAccordion sources={sources} />
      </div>
    </div>
  );
}
