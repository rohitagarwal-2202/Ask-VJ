import { useState, useEffect } from "react";
import type { HealthResponse } from "../types/api";

export function useHealth() {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let mounted = true;

    async function check() {
      try {
        const res = await fetch("/api/health");
        if (res.ok && mounted) {
          setHealth(await res.json());
        }
      } catch {
        if (mounted) {
          setHealth({ status: "degraded", warehouse: "unreachable", farvision: "unreachable", vjsales: "unreachable", vjop: "unreachable", llm: "unreachable", version: "?" });
        }
      }
    }

    check();
    const interval = setInterval(check, 30_000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  return health;
}
