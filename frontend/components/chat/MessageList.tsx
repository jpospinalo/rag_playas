import type { Message } from "@/lib/types";
import { AssistantBubble } from "@/components/chat/AssistantBubble";
import { UserBubble } from "@/components/chat/UserBubble";

interface MessageListProps {
  messages: Message[];
}

export function MessageList({ messages }: MessageListProps) {
  return (
    <>
      {messages.map(
        (msg) =>
          msg.text.length > 0 &&
          (msg.role === "user" ? (
            <UserBubble key={msg.id} text={msg.text} />
          ) : (
            <AssistantBubble
              key={msg.id}
              text={msg.text}
              sources={msg.sources ?? []}
            />
          )),
      )}
    </>
  );
}
