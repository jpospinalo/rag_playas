"use client";

import { useRef } from "react";
import { useChat } from "@/hooks/useChat";
import { ChatInput } from "@/components/chat/ChatInput";
import { EmptyState } from "@/components/chat/EmptyState";
import { LoadingBubble } from "@/components/chat/LoadingBubble";
import { MessageList } from "@/components/chat/MessageList";

export function ChatInterface() {
  const { messages, input, loading, error, messagesEndRef, setInput, submit } =
    useChat();

  /*
   * textareaRef lives here so ChatInterface can focus the input
   * when the user selects an example question.
   */
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleExampleSelect(question: string) {
    setInput(question);
    textareaRef.current?.focus();
  }

  const showEmptyState = messages.length === 0 && !loading && !error;

  return (
    <>
      <main
        id="main-content"
        className="flex flex-1 flex-col overflow-y-auto"
        aria-label="Conversación"
        aria-live="polite"
        aria-atomic="false"
      >
        {showEmptyState ? (
          <EmptyState onSelectExample={handleExampleSelect} />
        ) : (
          <div className="mx-auto w-full max-w-3xl flex-1 space-y-5 px-4 py-6">
            <MessageList messages={messages} />

            {loading && <LoadingBubble />}

            {error && (
              <div
                role="alert"
                className="animate-message-in rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
              >
                {error}
              </div>
            )}

            {/* Scroll-to-bottom sentinel */}
            <div ref={messagesEndRef} aria-hidden="true" />
          </div>
        )}
      </main>

      <ChatInput
        value={input}
        loading={loading}
        textareaRef={textareaRef}
        onChange={setInput}
        onSubmit={() => submit(input)}
      />
    </>
  );
}
