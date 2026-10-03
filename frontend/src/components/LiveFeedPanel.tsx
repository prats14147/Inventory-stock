// frontend/src/components/LiveFeedPanel.tsx
//
// The live sales feed plus the simulator controls that drive it. Events are
// pushed over the WebSocket (see hooks/useLiveStream.ts); the controls call
// the REST endpoints, and either transport works on its own.

import type { LiveSalesEvent } from "../types/live";

interface LiveFeedPanelProps {
  events: LiveSalesEvent[];
  connected: boolean;
  onTick: () => Promise<void>;
  busy?: boolean;
}

export default function LiveFeedPanel({ events, connected, onTick, busy }: LiveFeedPanelProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <span className={`flex items-center gap-2 text-xs ${connected ? "text-green-700" : "text-gray-500"}`}>
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-green-500" : "bg-gray-400"}`} />
          {connected ? "live" : "reconnecting..."}
        </span>
        <button
          type="button"
          onClick={onTick}
          disabled={busy}
          className="rounded bg-blue-600 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
        >
          {busy ? "Simulating..." : "Simulate one tick"}
        </button>
      </div>

      {events.length === 0 ? (
        <p className="rounded border border-dashed border-gray-300 p-4 text-sm text-gray-500">
          No live events yet.
        </p>
      ) : (
        <div className="max-h-64 overflow-y-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-gray-500">
              <tr>
                <th className="py-1">Time</th>
                <th className="py-1">Store</th>
                <th className="py-1">Product</th>
                <th className="py-1 text-right">Units</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id} className="border-t border-gray-100">
                  <td className="py-1 text-gray-500">{new Date(event.event_time).toLocaleTimeString()}</td>
                  <td className="py-1">{event.store_id}</td>
                  <td className="py-1 font-medium">{event.product_id}</td>
                  <td className="py-1 text-right">{event.units_sold}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
