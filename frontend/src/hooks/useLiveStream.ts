// frontend/src/hooks/useLiveStream.ts
//
// Subscribes to /api/live/ws and keeps a bounded, newest-first view of the
// live sales feed and the open alerts. Reconnects with a capped backoff so a
// dropped socket (restart, laptop sleep, network blip) self-heals without a
// page refresh. The REST endpoints in services/api.ts remain the fallback
// transport if websockets are unavailable.

import { useCallback, useEffect, useRef, useState } from "react";
import { acknowledgeAlert as acknowledgeAlertRequest, liveStreamUrl, websocketProtocols } from "../services/api";
import type { LiveFrame, LiveSalesEvent, StockoutAlert } from "../types/live";

const MAX_EVENTS = 25;
const MAX_ALERTS = 25;
const MAX_BACKOFF_MS = 15000;

export interface LiveStream {
  connected: boolean;
  events: LiveSalesEvent[];
  alerts: StockoutAlert[];
  unitsSold: number;
  lastFrameAt: string | null;
  reconnectAttempts: number;
  acknowledge: (alertId: number) => Promise<void>;
}

export function useLiveStream(backlog = 10): LiveStream {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<LiveSalesEvent[]>([]);
  const [alerts, setAlerts] = useState<StockoutAlert[]>([]);
  const [unitsSold, setUnitsSold] = useState(0);
  const [lastFrameAt, setLastFrameAt] = useState<string | null>(null);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;

    const open = () => {
      if (cancelled) return;
      const socket = new WebSocket(`${liveStreamUrl()}?backlog=${backlog}`, websocketProtocols());
      socketRef.current = socket;

      socket.onopen = () => {
        attempt = 0;
        if (!cancelled) {
          setConnected(true);
          setReconnectAttempts(0);
        }
      };

      socket.onmessage = (message) => {
        if (cancelled) return;
        let frame: LiveFrame;
        try {
          frame = JSON.parse(message.data as string) as LiveFrame;
        } catch {
          return; // never let a malformed frame break the stream
        }
        setLastFrameAt(new Date().toISOString());

        switch (frame.type) {
          case "sales_event": {
            const { type: _type, ...event } = frame;
            setEvents((previous) => [event, ...previous].slice(0, MAX_EVENTS));
            setUnitsSold((previous) => previous + event.units_sold);
            break;
          }
          case "alert": {
            const { type: _type, ...alert } = frame;
            // Re-alerted products replace their previous entry.
            setAlerts((previous) => [alert, ...previous.filter((a) => a.id !== alert.id)].slice(0, MAX_ALERTS));
            break;
          }
          case "alert_acknowledged":
            setAlerts((previous) => previous.filter((alert) => alert.id !== frame.id));
            break;
          default:
            break; // connected / ready / ping are informational only
        }
      };

      socket.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        attempt += 1;
        setReconnectAttempts(attempt);
        retryTimer = setTimeout(open, Math.min(1000 * 2 ** (attempt - 1), MAX_BACKOFF_MS));
      };

      socket.onerror = () => socket.close();
    };

    open();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket && socket.readyState <= WebSocket.OPEN) socket.close();
    };
  }, [backlog]);

  const acknowledge = useCallback(async (alertId: number) => {
    await acknowledgeAlertRequest(alertId);
    setAlerts((previous) => previous.filter((alert) => alert.id !== alertId));
  }, []);

  return { connected, events, alerts, unitsSold, lastFrameAt, reconnectAttempts, acknowledge };
}
