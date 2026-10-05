// frontend/src/types/chat.ts
// Kept in sync with backend/app/schemas/chat.py and app/nlp/intent.py

export type Intent =
  | "CURRENT_STOCK"
  | "LOW_STOCK"
  | "LOW_STOCK_FAST_SELLING"
  | "STOCK_HISTORY"
  | "TOP_SELLING"
  | "BOTTOM_SELLING"
  | "SALES_TREND"
  | "REVENUE_ANALYSIS"
  | "FINANCIAL_ANALYSIS"
  | "STORE_PROFITABILITY"
  | "PRODUCT_INFO"
  | "DEMAND_FORECAST"
  | "STOCKOUT_RISK"
  | "REORDER_RECOMMENDATION"
  | "CATEGORY_ANALYSIS"
  | "STORE_ANALYSIS"
  | "RECORD_SALE"
  | "RECEIVE_STOCK"
  | "ADJUST_STOCK"
  | "HELP"
  | "UNKNOWN";

export interface Entities {
  product_id: string | null;
  product_reference?: string | null;
  store_id: string | null;
  category: string | null;
  date: string | null;
  date_range: Record<string, string> | null;
  forecast_horizon: number | null;
  group_by?: string | null;
  granularity?: string | null;
}

export interface ChatRequest {
  message: string;
  /** Omit to let the backend start a new conversation. */
  session_id?: string | null;
}

export interface ChatResponse {
  message: string;
  intent: Intent;
  entities: Entities;
  // "rules" = keyword/regex layer, "llm" = Groq fallback for ambiguous input,
  // "context" = intent carried forward from the previous turn (backend
  // app/services/chat_service.py). Surfaced in the UI so a demo can show
  // exactly how a question was understood.
  parse_method: "rules" | "llm" | "context" | "command" | "knowledge";
  data: Record<string, unknown> | null;
  /** The conversation this turn belongs to -- persist it to keep chatting. */
  session_id: string;
  context: Record<string, unknown> | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
  /** Set when the turn failed to reach the assistant (network/API error), so
   *  the UI can style it as an error rather than a normal answer. */
  failed?: boolean;
}

// Mirrors backend/app/schemas/conversation.py SessionInfo / TurnInfo.
export interface ChatSessionInfo {
  session_id: string;
  user_id: string | null;
  turn_count: number;
  summary: string | null;
  /** First user message, backend-truncated -- sidebar label. */
  preview: string | null;
  active_entities: Record<string, string | null>;
  current_topic: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatTurn {
  turn_index: number;
  user_message: string;
  assistant_response: string | null;
  intent: string | null;
  entities: Record<string, unknown>;
  parse_method: string | null;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface ChatSessionHistory {
  session_id: string;
  turns: ChatTurn[];
  summary: string | null;
}

/** Rebuild display bubbles from a stored history (oldest first). */
export function messagesFromHistory(history: ChatSessionHistory): ChatMessage[] {
  const messages: ChatMessage[] = [];
  for (const turn of history.turns) {
    messages.push({ role: "user", text: turn.user_message });
    messages.push({
      role: "assistant",
      text: turn.assistant_response ?? "",
      response: {
        message: turn.assistant_response ?? "",
        intent: (turn.intent ?? "UNKNOWN") as Intent,
        entities: turn.entities as unknown as ChatResponse["entities"],
        parse_method: (turn.parse_method ?? "rules") as ChatResponse["parse_method"],
        data: turn.data,
        session_id: history.session_id,
        context: null,
      },
    });
  }
  return messages;
}
