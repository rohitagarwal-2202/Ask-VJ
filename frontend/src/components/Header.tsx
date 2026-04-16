import type { HealthResponse, UserInfo } from "../types/api";

interface HeaderProps {
  health: HealthResponse | null;
  onNewChat: () => void;
  user: UserInfo | null;
  onLogout: () => void;
}

interface ServiceStatus {
  label: string;
  status: string;
}

function StatusDot({ label, status }: ServiceStatus) {
  const isConnected = status === "connected" || status.startsWith("ready");
  const isError = status.startsWith("error");
  const color = isConnected
    ? "bg-green-400"
    : isError
      ? "bg-red-400"
      : "bg-yellow-400";

  return (
    <span className="group relative flex h-2 w-2" title={`${label}: ${status}`}>
      {isConnected && (
        <span
          className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${color}`}
        />
      )}
      <span className={`relative inline-flex h-2 w-2 rounded-full ${color}`} />
      <span className="pointer-events-none absolute bottom-full left-1/2 mb-2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-900 px-2 py-1 text-[10px] text-white opacity-0 transition-opacity group-hover:opacity-100">
        {label}: {status}
      </span>
    </span>
  );
}

function StatusBar({ health }: { health: HealthResponse | null }) {
  if (!health) {
    return (
      <div className="flex items-center gap-1.5">
        {["WH", "FV", "VJS", "VJOP", "LLM"].map((l) => (
          <StatusDot key={l} label={l} status="checking..." />
        ))}
      </div>
    );
  }

  const services: ServiceStatus[] = [
    { label: "Warehouse", status: health.warehouse },
    { label: "Farvision", status: health.farvision },
    { label: "VJ Sales", status: health.vjsales },
    { label: "VJOP", status: health.vjop },
    { label: "LLM", status: health.llm },
  ];

  return (
    <div className="flex items-center gap-1.5">
      {services.map((s) => (
        <StatusDot key={s.label} {...s} />
      ))}
    </div>
  );
}

export default function Header({ health, onNewChat, user, onLogout }: HeaderProps) {
  return (
    <header className="sticky top-0 z-50 flex h-12 items-center justify-between bg-brand px-4 md:h-14 md:px-6">
      <div className="flex items-center gap-2">
        <span className="h-5 w-1 rounded-full bg-accent" />
        <span className="text-lg font-bold tracking-tight text-white md:text-xl">
          Ask VJ
        </span>
      </div>

      <div className="flex items-center gap-3 md:gap-4">
        <StatusBar health={health} />

        {user && (
          <span className="hidden text-sm text-white/80 md:inline">
            {user.display_name}
          </span>
        )}

        <button
          onClick={onNewChat}
          className="rounded-md border border-white/40 px-3 py-1 text-xs font-medium text-white transition-colors hover:border-white hover:bg-white/10 md:text-sm"
        >
          New Chat
        </button>

        <button
          onClick={onLogout}
          className="px-1 text-xs text-white/60 transition-colors hover:text-white md:text-sm"
          title="Sign out"
        >
          Logout
        </button>
      </div>
    </header>
  );
}
