import type { HealthResponse, Message } from "../types/api";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
  onSendMessage: (q: string) => void;
  onSelectClarification?: (id: string, index: number) => void;
  health: HealthResponse | null;
}

const SUGGESTIONS = [
  "How many bookings this month?",
  "Outstanding aging by project",
  "Available 3 BHK inventory",
  "Collection efficiency this FY",
];

function WarehouseEmptyBanner() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 pb-20">
      <div className="mb-4 flex items-center gap-2">
        <span className="h-6 w-1.5 rounded-full bg-accent" />
        <h1 className="text-2xl font-bold text-brand md:text-3xl">Ask VJ</h1>
      </div>
      <div className="max-w-md rounded-lg border border-yellow-200 bg-yellow-50 px-6 py-4 text-center">
        <p className="mb-2 text-sm font-medium text-yellow-800">
          Data warehouse is initializing
        </p>
        <p className="text-xs text-yellow-600">
          The ETL pipeline hasn't run yet. Please run the pipeline to populate
          data before asking questions.
        </p>
        <code className="mt-3 block rounded bg-yellow-100 px-3 py-2 text-xs text-yellow-700">
          docker compose exec backend python -m backend.etl.run_pipeline
        </code>
      </div>
    </div>
  );
}

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
  onSelectClarification,
  health,
}: ChatWindowProps) {
  const warehouseEmpty = health?.warehouse === "empty";

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {warehouseEmpty && messages.length === 0 ? (
        <WarehouseEmptyBanner />
      ) : messages.length === 0 ? (
        <EmptyState onSend={onSendMessage} />
      ) : (
        <MessageList
          messages={messages}
          onSelectClarification={onSelectClarification}
          isLoading={isLoading}
        />
      )}
      <ChatInput onSend={onSendMessage} disabled={isLoading || warehouseEmpty} />
    </div>
  );
}
