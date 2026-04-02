import type { HealthResponse } from "../types/api";

interface HeaderProps {
  health: HealthResponse | null;
  onNewChat: () => void;
}

function StatusDot({ health }: { health: HealthResponse | null }) {
  const color = !health
    ? "bg-yellow-400"
    : health.status === "ok"
      ? "bg-green-400"
      : "bg-yellow-400";

  return (
    <span className="relative flex h-2.5 w-2.5">
      <span
        className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${color}`}
      />
      <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${color}`} />
    </span>
  );
}

export default function Header({ health, onNewChat }: HeaderProps) {
  return (
    <header className="sticky top-0 z-50 flex h-12 items-center justify-between bg-brand px-4 md:h-14 md:px-6">
      <div className="flex items-center gap-2">
        <span className="h-5 w-1 rounded-full bg-accent" />
        <span className="text-lg font-bold tracking-tight text-white md:text-xl">
          Ask VJ
        </span>
      </div>

      <div className="flex items-center gap-3 md:gap-4">
        <StatusDot health={health} />
        <button
          onClick={onNewChat}
          className="rounded-md border border-white/40 px-3 py-1 text-xs font-medium text-white transition-colors hover:border-white hover:bg-white/10 md:text-sm"
        >
          New Chat
        </button>
      </div>
    </header>
  );
}
