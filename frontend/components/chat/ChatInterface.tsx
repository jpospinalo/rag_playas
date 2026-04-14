"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useChat } from "@/hooks/useChat";
import { ChatHeader } from "@/components/chat/ChatHeader";
import { ChatInput } from "@/components/chat/ChatInput";
import { EmptyState } from "@/components/chat/EmptyState";
import { LoadingBubble } from "@/components/chat/LoadingBubble";
import { MessageList } from "@/components/chat/MessageList";

const SCROLL_THRESHOLD = 100; // px from bottom to consider "at bottom"

export function ChatInterface() {
  const { messages, input, loading, isStreaming, error, setInput, submit, resetChat } =
    useChat();

  /*
   * textareaRef lives here so ChatInterface can focus the input
   * when the user selects an example question.
   */
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Scroll container and sentinel refs
  const scrollContainerRef = useRef<HTMLElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Track whether user is pinned to the bottom. Using a ref avoids
  // re-renders on every scroll event; only the button visibility needs state.
  const isAtBottomRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);

  // Passive scroll listener — detects when user has scrolled away from bottom.
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    function handleScroll() {
      const distanceFromBottom =
        container!.scrollHeight - container!.scrollTop - container!.clientHeight;
      const atBottom = distanceFromBottom < SCROLL_THRESHOLD;

      if (isAtBottomRef.current !== atBottom) {
        isAtBottomRef.current = atBottom;
        setShowScrollButton(!atBottom);
      }
    }

    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => container.removeEventListener("scroll", handleScroll);
  }, []);

  // Auto-scroll to bottom when messages or loading state change,
  // but only when the user is already pinned to the bottom.
  useEffect(() => {
    if (isAtBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, loading]);

  const scrollToBottom = useCallback(() => {
    isAtBottomRef.current = true;
    setShowScrollButton(false);
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  function handleExampleSelect(question: string) {
    setInput(question);
    textareaRef.current?.focus();
  }

  function handleSubmit(question: string) {
    // Always snap to bottom when the user sends a new message.
    isAtBottomRef.current = true;
    setShowScrollButton(false);
    submit(question);
  }

  const showEmptyState = messages.length === 0 && !loading && !error;

  return (
    <div className="relative flex flex-1 flex-col overflow-hidden">
      <ChatHeader onNewChat={resetChat} />

      <main
        ref={scrollContainerRef}
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

            {/* Show loading bubble only while waiting for the first token */}
            {loading && !isStreaming && <LoadingBubble />}

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

      {/* Floating scroll-to-bottom button — visible when user has scrolled up */}
      {showScrollButton && messages.length > 0 && (
        <div className="pointer-events-none absolute bottom-0 left-0 right-0 z-10 flex justify-center pb-20">
          <button
            onClick={scrollToBottom}
            aria-label="Ir al final de la conversación"
            className="animate-scroll-btn-in pointer-events-auto flex items-center gap-1.5 rounded-full border border-border bg-surface px-3.5 py-2 text-xs font-medium text-muted shadow-md transition-colors duration-150 hover:border-accent hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="m6 9 6 6 6-6" />
            </svg>
            Ir al final
          </button>
        </div>
      )}

      <ChatInput
        value={input}
        loading={loading}
        textareaRef={textareaRef}
        onChange={setInput}
        onSubmit={() => handleSubmit(input)}
      />
    </div>
  );
}
