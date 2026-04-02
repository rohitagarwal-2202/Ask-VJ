import type { Message } from "../types/api";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
  onSendMessage: (q: string) => void;
}

const SUGGESTIONS = [
  "How many bookings this month?",
  "Outstanding aging by project",
  "Available 3 BHK inventory",
  "Collection efficiency this FY",
];

function EmptyState({ onSend }: { onSend: (q: string) => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 pb-20">
      <div className="mb-2 flex items-center gap-2">
        <span className="h-6 w-1.5 rounded-full bg-accent" />
        <h1 className="text-2xl font-bold text-brand md:text-3xl">Ask VJ</h1>
      </div>
      <p className="mb-8 text-sm text-gray-500 md:text-base">
        What would you like to know?
      </p>
      <div className="grid w-full max-w-xl grid-cols-1 gap-2 sm:grid-cols-2 md:gap-3">
        {SUGGESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => onSend(q)}
            className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-left text-sm text-gray-700 shadow-sm transition-all hover:border-accent hover:shadow-md"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function ChatWindow({
  messages,
  isLoading,
  onSendMessage,
}: ChatWindowProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {messages.length === 0 ? (
        <EmptyState onSend={onSendMessage} />
      ) : (
        <MessageList messages={messages} />
      )}
      <ChatInput onSend={onSendMessage} disabled={isLoading} />
    </div>
  );
}
