"use client";

import { useRef, useState } from "react";
import { queryRagStream } from "@/lib/api";
import type { Message } from "@/lib/types";

export interface UseChatReturn {
  messages: Message[];
  input: string;
  loading: boolean;
  isStreaming: boolean;
  error: string | null;
  setInput: (value: string) => void;
  submit: (question: string) => Promise<void>;
  resetChat: () => void;
}

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Track whether the first token has been received to flip isStreaming exactly once.
  const streamingStartedRef = useRef(false);

  async function submit(question: string): Promise<void> {
    const q = question.trim();
    if (!q || loading) return;

    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", text: q },
    ]);
    setInput("");
    setLoading(true);
    setIsStreaming(false);
    setError(null);
    streamingStartedRef.current = false;

    // Insert assistant placeholder before streaming starts so the user
    // sees the response area appear immediately.
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", text: "", sources: [] },
    ]);

    try {
      for await (const event of queryRagStream({ question: q })) {
        if (event.type === "token") {
          // Flip to streaming on first token so LoadingBubble disappears.
          if (!streamingStartedRef.current) {
            streamingStartedRef.current = true;
            setIsStreaming(true);
          }
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, text: m.text + event.content }
                : m
            )
          );
        } else if (event.type === "sources") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, sources: event.sources } : m
            )
          );
        } else if (event.type === "error") {
          throw new Error(event.detail);
        }
      }
    } catch (err) {
      // Remove the empty placeholder on error so the UI stays clean.
      setMessages((prev) => prev.filter((m) => m.id !== assistantId));
      setError(
        err instanceof Error
          ? err.message
          : "Error de conexión. Compruebe que el servidor está activo."
      );
    } finally {
      setLoading(false);
      setIsStreaming(false);
    }
  }

  function resetChat(): void {
    setMessages([]);
    setInput("");
    setLoading(false);
    setIsStreaming(false);
    setError(null);
    streamingStartedRef.current = false;
  }

  return { messages, input, loading, isStreaming, error, setInput, submit, resetChat };
}
