import type { Metadata } from "next";
import { ChatHeader } from "@/components/chat/ChatHeader";
import { ChatInterface } from "@/components/chat/ChatInterface";

export const metadata: Metadata = {
  title: "Consulta | RAG Playas",
  description:
    "Realice consultas jurídicas sobre jurisprudencia colombiana en materia de playas, bienes de uso público costero y derecho marítimo.",
  robots: { index: false, follow: false },
};

export default function ChatPage() {
  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background">
      <ChatHeader />
      <ChatInterface />
    </div>
  );
}
