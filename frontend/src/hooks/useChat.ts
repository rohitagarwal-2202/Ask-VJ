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

      if (data.type === "clarification" && data.clarification_id && data.clarification_options) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: data.answer,
                  response: data,
                  isLoading: false,
                  clarification: {
                    clarification_id: data.clarification_id!,
                    options: data.clarification_options!,
                  },
                }
              : m,
          ),
        );
      } else {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: data.answer, response: data, isLoading: false }
              : m,
          ),
        );
      }
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

  const selectClarification = useCallback(
    async (clarificationId: string, optionIndex: number) => {
      setIsLoading(true);

      // Find the clarification message and add a loading indicator after it
      const resolveId = generateId();
      const loadingMessage: Message = {
        id: resolveId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        isLoading: true,
      };

      setMessages((prev) => {
        // Remove the clarification from the original message and append loading
        const updated = prev.map((m) =>
          m.clarification?.clarification_id === clarificationId
            ? { ...m, clarification: undefined }
            : m,
        );
        return [...updated, loadingMessage];
      });

      try {
        const res = await apiFetch("/clarify", {
          method: "POST",
          body: JSON.stringify({
            clarification_id: clarificationId,
            option_index: optionIndex,
          }),
        });

        if (!res.ok) throw new Error(`Server error: ${res.status}`);

        const data: QueryResponse = await res.json();

        setMessages((prev) =>
          prev.map((m) =>
            m.id === resolveId
              ? { ...m, content: data.answer, response: data, isLoading: false }
              : m,
          ),
        );
      } catch {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === resolveId
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
    },
    [],
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    sessionId.current = generateId();
  }, []);

  return { messages, isLoading, sendMessage, clearChat, selectClarification };
}
