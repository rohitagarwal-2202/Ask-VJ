import { useState, useCallback, useRef } from "react";
import type { Message, QueryResponse } from "../types/api";
import { apiFetch } from "../lib/api";

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2);
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const sessionId = useRef(generateId());

  const sendMessage = useCallback(async (question: string) => {
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: question,
      timestamp: new Date(),
    };

    const assistantId = generateId();
    const loadingMessage: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
      isLoading: true,
    };

    setMessages((prev) => [...prev, userMessage, loadingMessage]);
    setIsLoading(true);

    try {
      const res = await apiFetch("/query", {
        method: "POST",
        body: JSON.stringify({
          question,
          session_id: sessionId.current,
        }),
      });

      if (!res.ok) throw new Error(`Server error: ${res.status}`);

      const data: QueryResponse = await res.json();

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: data.answer, response: data, isLoading: false }
            : m,
        ),
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: "Something went wrong. Please try again.",
                isLoading: false,
                isError: true,
              }
            : m,
        ),
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  const clearChat = useCallback(() => {
    setMessages([]);
    sessionId.current = generateId();
  }, []);

  return { messages, isLoading, sendMessage, clearChat };
}
