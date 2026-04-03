export interface QueryRequest {
  question: string;
  session_id?: string;
}

export interface QueryResponse {
  answer: string;
  confidence: "high" | "medium" | "low";
  confidence_score: number;
  data_sources: string[];
  filters_applied: Record<string, string>;
  intent: string;
  last_sync: string | null;
  response_time_ms: number;
  warnings: string[];
}

export interface HealthResponse {
  status: "ok" | "degraded";
  warehouse: string;
  llm: string;
  version: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  response?: QueryResponse;
  isLoading?: boolean;
  isError?: boolean;
}

// Auth types
export interface UserInfo {
  user_id: number;
  phone: string;
  display_name: string;
  role: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserInfo;
}
