// frontend/src/hooks/useChatStream.ts
//
// Streaming transport for the chat page (backend: app/routers/ws.py).
//
// Uses /api/chat/ws when it is reachable -- the answer text streams in token
// by token and the UI can show which pipeline stage is running -- and silently
// degrades to the plain REST endpoint (POST /api/chat) when websockets are
// blocked by a proxy or the socket cannot be opened. Both transports return
// the SAME verified payload; only the delivery differs.
//
// Token frames are provisional: the final `chat_response` frame is
// authoritative and is what the transcript keeps (see routers/ws.py).

import { useCallback, useEffect, useRef, useState } from "react";
import { chatStreamUrl, postChat } from "../services/api";
import type { ChatStreamFrame } from "../types/live";
import type { ChatResponse, Entities, Intent } from "../types/chat";

const MAX_BACKOFF_MS = 10000;

export interface ChatStream {
  connected: boolean;
  /** The conversation the socket is bound to (null until announced). */
  sessionId: string | null;
  /** Live pipeline stage for the in-flight turn, e.g. "querying_database". */
  stage: string | null;
  /** Provisional text streamed so far for the in-flight turn. */
  pendingText: string;
  transport: "websocket" | "rest";
  sendMessage: (text: string) => Promise<ChatResponse>;
  /** Switch to another session: reconnects the socket bound to it. */
  switchSession: (sessionId: string | null) => void;
}

interface PendingTurn {
  resolve: (response: ChatResponse) => void;
  reject: (error: Error) => void;
}

const EMPTY_ENTITIES: Entities = {
  product_id: null,
  store_id: null,
  category: null,
  date: null,
  date_range: null,
  forecast_horizon: null,
};

export function useChatStream(initialSessionId: string | null = null): ChatStream {
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId);
  const [stage, setStage] = useState<string | null>(null);
  const [pendingText, setPendingText] = useState("");
  const [transport, setTransport] = useState<"websocket" | "rest">("websocket");
  const socketRef = useRef<WebSocket | null>(null);
  const pendingRef = useRef<PendingTurn | null>(null);
  const sessionIdRef = useRef<string | null>(initialSessionId);
  // Re-open generation: switchSession() bumps this, the effect tears down
  // the old socket and opens a fresh one bound to the requested session.
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;

    const open = () => {
      if (cancelled) return;
      const socket = new WebSocket(chatStreamUrl(sessionIdRef.current));
      socketRef.current = socket;

      socket.onopen = () => {
        attempt = 0;
        if (!cancelled) setConnected(true);
      };

      socket.onmessage = (message) => {
        if (cancelled) return;
        let frame: ChatStreamFrame;
        try {
          frame = JSON.parse(message.data as string) as ChatStreamFrame;
        } catch {
          return;
        }

        switch (frame.type) {
          case "session_created":
            sessionIdRef.current = frame.session_id;
            setSessionId(frame.session_id);
            break;
          case "status":
            setStage(frame.stage);
            break;
          case "token":
            setPendingText((previous) => previous + frame.text);
            break;
          case "chat_response": {
            const pending = pendingRef.current;
            pendingRef.current = null;
            setStage(null);
            setPendingText("");
            sessionIdRef.current = frame.session_id;
            setSessionId(frame.session_id);
            pending?.resolve({
              message: frame.message,
              intent: (frame.intent ?? "UNKNOWN") as Intent,
              entities: { ...EMPTY_ENTITIES, ...(frame.entities as Partial<Entities>) },
              parse_method: (frame.parse_method ?? "rules") as ChatResponse["parse_method"],
              data: frame.data ?? null,
              session_id: frame.session_id,
              context: frame.context ?? null,
            });
            break;
          }
          case "error": {
            const pending = pendingRef.current;
            pendingRef.current = null;
            setStage(null);
            setPendingText("");
            pending?.reject(new Error(frame.message));
            break;
          }
          default:
            break; // pong / context_reset
        }
      };

      socket.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        // An in-flight turn can't be replayed on a new socket; fail it so the
        // caller falls back to REST for that message.
        const pending = pendingRef.current;
        pendingRef.current = null;
        pending?.reject(new Error("The live connection dropped."));
        attempt += 1;
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
  }, [generation]);

  const sendViaRest = useCallback(async (text: string): Promise<ChatResponse> => {
    setTransport("rest");
    const response = await postChat(text, sessionIdRef.current);
    sessionIdRef.current = response.session_id;
    setSessionId(response.session_id);
    return response;
  }, []);

  const sendMessage = useCallback(
    async (text: string): Promise<ChatResponse> => {
      const socket = socketRef.current;
      if (socket && socket.readyState === WebSocket.OPEN) {
        setStage(null);
        setPendingText("");
        try {
          return await new Promise<ChatResponse>((resolve, reject) => {
            pendingRef.current = { resolve, reject };
            socket.send(JSON.stringify({ type: "chat", message: text }));
          });
        } catch {
          // Socket dropped mid-turn or the server sent an error frame.
          // REST returns the same verified payload.
          return sendViaRest(text);
        }
      }

      return sendViaRest(text);
    },
    [sendViaRest]
  );

  const switchSession = useCallback((next: string | null) => {
    // Fail any in-flight turn -- it belongs to the old session.
    const pending = pendingRef.current;
    pendingRef.current = null;
    pending?.reject(new Error("Switched conversation."));
    sessionIdRef.current = next;
    setSessionId(next);
    setStage(null);
    setPendingText("");
    setTransport("websocket");
    // Triggers the effect to reconnect with the new ?session_id=.
    setGeneration((g) => g + 1);
  }, []);

  return { connected, sessionId, stage, pendingText, transport, sendMessage, switchSession };
}
