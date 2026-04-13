export interface SourceDocument {
  content: string;
  source: string;
  title: string;
  metadata: Record<string, unknown>;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: SourceDocument[];
}

export interface QueryRequest {
  question: string;
  /** Number of context fragments (1–8, default 4) */
  k?: number;
  /** Initial retriever candidates (4–20, default 8) */
  k_candidates?: number;
}

export interface QueryResponse {
  answer: string;
  sources: SourceDocument[];
}
