"use client";

import { useEffect, useRef, useState } from "react";
import { queryRag } from "@/lib/api";
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

    try {
      const data = await queryRag({ question: q });
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: data.answer,
          sources: data.sources,
        },
      ]);
    } catch (err) {
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
