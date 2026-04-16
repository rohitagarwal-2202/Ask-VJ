export interface QueryRequest {
  question: string;
  session_id?: string;
}

export interface ClarificationOption {
  label: string;
  description: string;
  refined_query: string;
}

export interface TableData {
  columns: string[];
  rows: (string | number | null)[][];
  row_count: number;
  truncated: boolean;
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
  sql_query?: string;
  table_data?: TableData;
  type?: "answer" | "clarification";
  clarification_id?: string;
  clarification_options?: ClarificationOption[];
}

export interface HealthResponse {
  status: "ok" | "degraded";
  warehouse: string;
  farvision: string;
  vjsales: string;
  vjop: string;
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
  clarification?: {
    clarification_id: string;
    options: ClarificationOption[];
  };
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
