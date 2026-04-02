import { useState } from "react";
import type { Message } from "../types/api";

interface MessageBubbleProps {
  message: Message;
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1 px-1 py-2">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-2 w-2 rounded-full bg-gray-400"
          style={{
            animation: "typing 1.2s infinite",
            animationDelay: `${i * 0.2}s`,
          }}
        />
      ))}
      <style>{`
        @keyframes typing {
          0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
          30% { opacity: 1; transform: translateY(-4px); }
        }
      `}</style>
    </div>
  );
}

function ErrorIcon() {
  return (
    <svg
      className="h-4 w-4 shrink-0 text-error"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`}
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function ConfidenceBadge({ level }: { level: "high" | "medium" | "low" }) {
  const styles = {
    high: "bg-green-100 text-green-700",
    medium: "bg-yellow-100 text-yellow-700",
    low: "bg-red-100 text-red-700",
  };
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${styles[level]}`}
    >
      {level}
    </span>
  );
}

function MetadataBar({ message }: { message: Message }) {
  const [open, setOpen] = useState(false);
  const r = message.response;
  if (!r) return null;

  return (
    <div className="mt-2 border-t border-gray-100 pt-1">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-xs text-gray-400 transition-colors hover:text-gray-600"
      >
        Details
        <ChevronIcon open={open} />
      </button>

      {open && (
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            Confidence: <ConfidenceBadge level={r.confidence} />
          </span>
          <span>{r.response_time_ms}ms</span>
          <span>
            Intent:{" "}
            <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-xs">
              {r.intent}
            </code>
          </span>
          {r.data_sources.length > 0 && (
            <span className="flex flex-wrap gap-1">
              {r.data_sources.map((src) => (
                <span
                  key={src}
                  className="rounded bg-gray-100 px-1.5 py-0.5 text-xs"
                >
                  {src}
                </span>
              ))}
            </span>
          )}
          {r.warnings.length > 0 && (
            <div className="w-full">
              {r.warnings.map((w, i) => (
                <p key={i} className="text-xs text-warning">
                  {w}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[90%] rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-sm text-white md:max-w-[80%]">
          {message.content}
        </div>
      </div>
    );
  }

  const bgClass = message.isError
    ? "bg-red-50 border border-red-200"
    : "bg-white border border-gray-100 shadow-sm";

  return (
    <div className="flex justify-start">
      <div
        className={`max-w-[90%] rounded-2xl rounded-bl-md px-4 py-2.5 text-sm text-gray-800 md:max-w-[80%] ${bgClass}`}
      >
        {message.isLoading ? (
          <TypingDots />
        ) : (
          <>
            <div className="flex items-start gap-2">
              {message.isError && <ErrorIcon />}
              <p className="whitespace-pre-wrap">{message.content}</p>
            </div>
            <MetadataBar message={message} />
          </>
        )}
      </div>
    </div>
  );
}
