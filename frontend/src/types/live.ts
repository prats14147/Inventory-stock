// frontend/src/types/live.ts
//
// Types for the real-time layer (live sales events, proactive alerts, and
// the WebSocket frames the live stream sends).

export interface LiveSalesEvent {
  id: number;
  event_time: string;
  store_id: string;
  product_id: string;
  units_sold: number;
  unit_price: number;
  source: string;
}

export type AlertSeverity = "CRITICAL" | "WARNING";

export interface StockoutAlert {
  id: number;
  created_at: string;
  product_id: string;
  severity: AlertSeverity;
  kind: string;
  message: string;
  current_inventory: number;
  live_units_sold: number;
  projected_inventory: number;
  forecast_lead_time_demand: number;
  required_inventory: number;
  lead_time_days: number;
  acknowledged: boolean;
  acknowledged_at: string | null;
  trigger: string;
}

export interface LiveHubStats {
  subscribers: number;
  frames_published: number;
  max_buffer: number;
}

export interface SimulatorStatus {
  running: boolean;
  ticks: number;
  tick_seconds: number;
  events_per_tick: number;
  alert_cooldown_seconds: number;
  last_tick: { tick_at: string; events: LiveSalesEvent[]; alerts: StockoutAlert[]; suppressed_alerts: number } | null;
  hub: LiveHubStats;
}

export interface LiveSummary {
  simulator: SimulatorStatus;
  live_events: number;
  live_units_sold: number;
  open_alerts: number;
  critical_alerts: number;
  hub: LiveHubStats;
  alert_cooldown_seconds: number;
}

// Frames pushed over /api/live/ws. `type` discriminates the union, so a
// switch on it is exhaustive for TypeScript.
export type LiveFrame =
  | { type: "connected"; subscribers: number; backlog_size: number }
  | { type: "ready" }
  | { type: "ping" }
  | ({ type: "sales_event" } & LiveSalesEvent)
  | ({ type: "alert" } & StockoutAlert)
  | { type: "alert_acknowledged"; id: number; product_id: string };

// Frames pushed over /api/chat/ws (streaming chat).
export type ChatStreamFrame =
  | { type: "session_created"; session_id: string }
  | { type: "status"; stage: string; session_id: string }
  | { type: "token"; text: string; session_id: string }
  | { type: "pong"; session_id: string }
  | { type: "context_reset"; session_id: string }
  | {
      type: "chat_response";
      message: string;
      intent: string | null;
      entities: Record<string, string | null>;
      parse_method: string;
      data: Record<string, unknown> | null;
      session_id: string;
      context: Record<string, unknown> | null;
    }
  | { type: "error"; code: string; message: string; session_id?: string | null };
