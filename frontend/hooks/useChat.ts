"use client";

import { useEffect, useRef, useState } from "react";
import { queryRagStream } from "@/lib/api";
import type { Message } from "@/lib/types";

export interface UseChatReturn {
  messages: Message[];
  input: string;
  loading: boolean;
  error: string | null;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  setInput: (value: string) => void;
  submit: (question: string) => Promise<void>;
}

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function submit(question: string): Promise<void> {
    const q = question.trim();
    if (!q || loading) return;

    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", text: q },
    ]);
    setInput("");
    setLoading(true);
    setError(null);

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
    }
  }

  return { messages, input, loading, error, messagesEndRef, setInput, submit };
}
