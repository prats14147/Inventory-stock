// frontend/src/pages/Chatbot.tsx

import { useState, useRef, useEffect } from "react";
import { postChat, ApiError } from "../services/api";
import type { ChatMessage } from "../types/chat";

const EXAMPLE_QUESTIONS = [
  "How much stock do we have for P0001?",
  "Which products are low on stock?",
  "What are our top-selling products?",
  "Forecast P0001 for the next 14 days.",
  "Will P0007 run out of stock?",
  "How much should we reorder for P0007?",
];

export default function Chatbot() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(text: string) {
    if (!text.trim() || loading) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setLoading(true);
    try {
      const response = await postChat(text);
      setMessages((prev) => [...prev, { role: "assistant", text: response.message, response }]);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Something went wrong reaching the assistant.";
      setMessages((prev) => [...prev, { role: "assistant", text: message }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      <h1 className="mb-3 text-xl font-semibold">Chatbot</h1>

      <div className="flex-1 overflow-y-auto rounded-lg border bg-white p-4 shadow-sm">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-sm text-gray-500">Try asking:</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  className="rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs text-brand-700 hover:bg-brand-100"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-3">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                  m.role === "user" ? "bg-brand-600 text-white" : "bg-gray-100 text-gray-800"
                }`}
              >
                {m.text}
                {m.response?.intent === "STOCKOUT_RISK" && m.response.data && (
                  <div className="mt-2 rounded bg-white/60 p-2 text-xs text-gray-700">
                    Risk: {String(m.response.data.risk)}
                  </div>
                )}
              </div>
            </div>
          ))}
          {loading && <div className="text-sm text-gray-400">Thinking...</div>}
        </div>
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
          className="flex-1 rounded-md border px-3 py-2 text-sm"
          placeholder="Ask about stock, sales, forecasts, stockout risk, or reorder..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700" disabled={loading}>
          Send
        </button>
      </form>
    </div>
  );
}
