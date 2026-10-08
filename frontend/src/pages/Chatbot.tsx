// frontend/src/pages/Chatbot.tsx

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  createChatSession,
  deleteChatSession,
  getChatSessionHistory,
  listChatSessions,
} from "../services/api";
import { useChatStream } from "../hooks/useChatStream";
import type { ChatMessage, ChatSessionInfo } from "../types/chat";
import { messagesFromHistory } from "../types/chat";
import ChatAnswerCard from "../components/ChatAnswerCard";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import { ErrorState, LoadingState } from "../components/LoadingError";

const STORAGE_KEY = "inventoryai:chat:session_id";

const EXAMPLE_QUESTIONS = [
  "How much stock do we have for P0001?",
  "Which products are low on stock?",
  "What are our top-selling products?",
  "Forecast P0001 for the next 14 days.",
  "Will P0007 run out of stock?",
  "How much should we reorder for P0007?",
];

// Human labels for the pipeline stages the backend reports while it works
// (see STAGE_* constants in app/services/chat_service.py).
const STAGE_LABELS: Record<string, string> = {
  analyzing_request: "Understanding the question...",
  querying_database: "Querying the database...",
  phrasing_response: "Writing the answer...",
};

function sessionLabel(session: ChatSessionInfo): string {
  if (session.preview) return session.preview;
  if (session.summary) return session.summary.slice(0, 80);
  return `Chat ${session.session_id.slice(0, 8)}`;
}

export default function Chatbot() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<ChatSessionInfo[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const restoredRef = useRef(false);
  const { connected, sessionId, stage, pendingText, transport, sendMessage, switchSession } = useChatStream(
    typeof localStorage !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null
  );

  // Persist the active session so a refresh resumes the same conversation.
  useEffect(() => {
    if (sessionId) localStorage.setItem(STORAGE_KEY, sessionId);
  }, [sessionId]);

  const refreshSessions = useCallback(async () => {
    setSessionsError(null);
    try {
      const body = await listChatSessions();
      setSessions(body.sessions);
    } catch (err) {
      // The chat still works without the sidebar, but say so instead of
      // rendering a permanently empty "no conversations" list.
      setSessionsError(err instanceof ApiError ? err.message : "Couldn't load your conversations.");
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  // On first connect, resume the stored session history (if any).
  useEffect(() => {
    if (restoredRef.current || !connected || !sessionId) return;
    restoredRef.current = true;
    setLoadingHistory(true);
    getChatSessionHistory(sessionId)
      .then((history) => {
        if (history.turns.length > 0) setMessages(messagesFromHistory(history));
      })
      .catch(() => {
        // Brand-new or expired session: start with a blank transcript.
      })
      .finally(() => setLoadingHistory(false));
  }, [connected, sessionId]);

  const selectSession = useCallback(
    async (nextId: string | null) => {
      if (nextId === sessionId || loading) return;
      setMessages([]);
      if (nextId) {
        setLoadingHistory(true);
        try {
          const history = await getChatSessionHistory(nextId);
          setMessages(messagesFromHistory(history));
        } catch {
          setMessages([]);
        } finally {
          setLoadingHistory(false);
        }
      }
      switchSession(nextId);
      void refreshSessions();
    },
    [loading, refreshSessions, sessionId, switchSession]
  );

  const newChat = useCallback(async () => {
    if (loading) return;
    try {
      const created = await createChatSession();
      localStorage.setItem(STORAGE_KEY, created.session_id);
      setMessages([]);
      switchSession(created.session_id);
      void refreshSessions();
    } catch {
      // Fall back to a local reset: next send creates a server session.
      setMessages([]);
      localStorage.removeItem(STORAGE_KEY);
      switchSession(null);
    }
  }, [loading, refreshSessions, switchSession]);

  const removeSession = useCallback(
    async (id: string) => {
      try {
        await deleteChatSession(id);
      } catch {
        return;
      }
      if (id === sessionId) {
        setMessages([]);
        localStorage.removeItem(STORAGE_KEY);
        switchSession(null);
      }
      void refreshSessions();
    },
    [refreshSessions, sessionId, switchSession]
  );

  const send = useCallback(
    async (text: string) => {
      if (!text.trim() || loading) return;
      setMessages((prev) => [...prev, { role: "user", text }]);
      setInput("");
      setLoading(true);
      try {
        const response = await sendMessage(text);
        setMessages((prev) => [...prev, { role: "assistant", text: response.message, response }]);
        void refreshSessions();
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : "Something went wrong reaching the assistant.";
        setMessages((prev) => [...prev, { role: "assistant", text: message, failed: true }]);
      } finally {
        setLoading(false);
      }
    },
    [loading, refreshSessions, sendMessage]
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pendingText, stage]);

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* Session sidebar -- the Phase 11 memory UI: list, resume, delete. */}
      <aside className="hidden w-64 shrink-0 flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm md:flex">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <span className="text-sm font-medium text-gray-700">Conversations</span>
          <button
            onClick={newChat}
            disabled={loading}
            className="rounded-md bg-brand-600 px-2 py-1 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            + New
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {loadingSessions ? (
            <p className="px-2 py-1 text-xs text-gray-400">Loading...</p>
          ) : sessionsError ? (
            <div className="px-1">
              <ErrorState message={sessionsError} onRetry={() => void refreshSessions()} />
            </div>
          ) : sessions.length === 0 ? (
            <EmptyState
              title="No saved conversations"
              hint="Start chatting and your conversations will be listed here, ready to resume."
            />
          ) : (
            <ul className="space-y-1">
              {sessions.map((s) => (
                <li
                  key={s.session_id}
                  className={`group flex items-center gap-1 rounded-md px-2 py-1.5 text-xs ${
                    s.session_id === sessionId ? "bg-brand-50 text-brand-800" : "text-gray-600 hover:bg-gray-100"
                  }`}
                >
                  <button onClick={() => selectSession(s.session_id)} className="min-w-0 flex-1 truncate text-left">
                    <span className="block truncate font-medium">{sessionLabel(s)}</span>
                    <span className="block text-[11px] opacity-60">
                      {s.turn_count} turn{s.turn_count === 1 ? "" : "s"}
                    </span>
                  </button>
                  <button
                    onClick={() => removeSession(s.session_id)}
                    title="Delete conversation"
                    className="hidden shrink-0 rounded px-1 text-gray-400 hover:bg-red-50 hover:text-red-600 group-hover:block"
                  >
                    x
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      {/* Chat column */}
      <div className="flex min-w-0 flex-1 flex-col">
      <PageHeader
        title="Chatbot"
        subtitle="Ask about stock, sales, forecasts, stockout risk, or reorders. Every answer is computed from the database and the saved models."
        actions={
          <>
            <button
              onClick={newChat}
              disabled={loading}
              className="rounded-full bg-gray-100 px-2.5 py-1 font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-50 md:hidden"
            >
              + New chat
            </button>
            <span className="rounded-full bg-gray-100 px-2.5 py-1 font-medium text-gray-700">
              {transport === "websocket" ? "streaming" : "rest fallback"}
            </span>
            <span
              className={`flex items-center gap-1.5 ${connected ? "text-green-700" : "text-gray-500"}`}
              title={connected ? "Live WebSocket connection" : "Reconnecting..."}
            >
              <span className={`h-2 w-2 rounded-full ${connected ? "bg-green-500" : "bg-gray-400"}`} />
              {connected ? "live connection" : "connecting..."}
            </span>
          </>
        }
      />

      <div className="mt-3 flex-1 overflow-y-auto rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        {loadingHistory ? (
          <LoadingState label="Loading conversation..." />
        ) : (
        <>
        {messages.length === 0 && (
          <EmptyState
            title="Ask a question to get started"
            hint="Every answer comes from the live database and the trained forecast model, never from a guess. The assistant remembers this conversation, so follow-ups like “forecast it” work."
            action={
              <div className="flex flex-wrap justify-center gap-2">
                {EXAMPLE_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    className="rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 hover:bg-brand-100"
                  >
                    {q}
                  </button>
                ))}
              </div>
            }
          />
        )}

        <div className="space-y-3">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              {m.failed ? (
                <div className="max-w-[80%]">
                  <ErrorState message={m.text} />
                </div>
              ) : (
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                  m.role === "user" ? "bg-brand-600 text-white" : "bg-gray-100 text-gray-800"
                }`}
              >
                {m.text}
                {m.response?.parse_method === "context" && (
                  <div className="mt-2 text-xs opacity-70">intent carried over from the previous turn</div>
                )}
                {m.response && <ChatAnswerCard response={m.response} />}
                {Array.isArray(m.response?.data?.sources) && m.response.data.sources.length > 0 && (
                  <div className="mt-2 text-[11px] text-gray-500">
                    Based on: {m.response.data.sources.map((source) => {
                      const item = source as { source?: string; section?: string };
                      return `${item.section ?? "Project notes"} (${item.source ?? "documentation"})`;
                    }).join(" · ")}
                  </div>
                )}
                {m.response?.intent === "RECORD_SALE" &&
                  (m.response.data as Record<string, unknown> | null)?.sale_status === "awaiting_confirmation" && (
                    <div className="mt-3 flex gap-2 border-t border-gray-200 pt-2">
                      <button
                        onClick={() => void send("confirm sale")}
                        disabled={loading}
                        className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-green-700 disabled:opacity-50"
                      >
                        Confirm sale
                      </button>
                      <button
                        onClick={() => void send("cancel sale")}
                        disabled={loading}
                        className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-semibold text-gray-700 hover:bg-white disabled:opacity-50"
                      >
                        Cancel
                      </button>
                    </div>
                  )}
              </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="max-w-[80%] rounded-lg bg-gray-100 px-3 py-2 text-sm text-gray-800">
                {pendingText ? (
                  <>
                    {pendingText}
                    <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-gray-400 align-middle" />
                  </>
                ) : (
                  <span className="text-gray-500">
                    {stage ? STAGE_LABELS[stage] ?? `${stage}...` : "Thinking..."}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-gray-50"
          placeholder="Ask about stock, sales, forecasts, stockout risk, or reorder... (Enter to send, Shift+Enter is not supported)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
          aria-label="Message"
        />
        <button
          type="submit"
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={loading || !input.trim()}
        >
          Send
        </button>
      </form>
      </div>
    </div>
  );
}
