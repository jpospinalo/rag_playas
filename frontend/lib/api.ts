import type { QueryRequest, QueryResponse, StreamEvent } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

export async function queryRag(
  request: QueryRequest
): Promise<QueryResponse> {
  const res = await fetch(`${API_URL}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(
      detail.trim() || `Error del servidor (${res.status})`
    );
  }

  return res.json() as Promise<QueryResponse>;
}

/**
 * Async generator that connects to the SSE streaming endpoint and yields
 * typed events as they arrive.
 *
 * Usage:
 *   for await (const event of queryRagStream({ question: "..." })) {
 *     if (event.type === "token") { ... }
 *     else if (event.type === "sources") { ... }
 *   }
 */
export async function* queryRagStream(
  request: QueryRequest
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${API_URL}/api/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(
      detail.trim() || `Error del servidor (${res.status})`
    );
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by double newlines
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data: ")) continue;

        const data = line.slice(6);
        if (data === "[DONE]") return;

        yield JSON.parse(data) as StreamEvent;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
