// frontend/src/components/AlertsDrawer.tsx
//
// Notification drawer for proactive StockoutAlert events. Reads the durable
// REST snapshot (/api/live/alerts) so it works even when the WebSocket is
// down, and acknowledges through the same endpoint the Live page uses.

import { useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";
import { acknowledgeAlert, getLiveAlerts } from "../services/api";

export function AlertsBell() {
  const [open, setOpen] = useState(false);
  const { data } = useApi(() => getLiveAlerts(false, 50), [open]);
  const count = data?.count ?? 0;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="relative shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900"
        aria-label={`Open alerts (${count} open)`}
        title="Stockout alerts"
      >
        🔔 Alerts
        {count > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-600 px-1 text-[11px] font-bold text-white">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>
      {open && (
        <AlertsDrawer
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

export default function AlertsDrawer({ onClose }: { onClose: () => void }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState("");
  const { data, loading, error } = useApi(() => getLiveAlerts(false, 50), [refreshKey]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function acknowledge(id: number) {
    setBusyId(id);
    setActionError("");
    try {
      await acknowledgeAlert(id);
      setRefreshKey((k) => k + 1);
    } catch {
      setActionError(`Could not acknowledge alert #${id}. Try again.`);
    } finally {
      setBusyId(null);
    }
  }

  const alerts = data?.alerts ?? [];

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Stockout alerts">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Alerts</h2>
            <p className="text-xs text-gray-500">{alerts.length} open · from /api/live/alerts</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-300 px-2.5 py-1 text-sm font-medium text-gray-600 hover:bg-gray-50"
          >
            Close ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {loading && <p className="text-sm text-gray-500">Loading alerts…</p>}
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          {actionError && <p role="alert" className="mb-2 text-sm text-red-700">{actionError}</p>}
          {!loading && !error && alerts.length === 0 && (
            <p className="rounded border border-dashed border-gray-300 p-4 text-sm text-gray-500">
              No open alerts. Start the simulator on the Live page to generate traffic.
            </p>
          )}
          <ul className="space-y-3">
            {alerts.map((alert) => (
              <li
                key={alert.id}
                className={`rounded border p-3 ${alert.severity === "CRITICAL" ? "border-red-200 bg-red-50" : "border-amber-200 bg-amber-50"}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-gray-900">
                      {alert.severity} · {alert.product_id}
                    </p>
                    <p className="mt-1 text-sm text-gray-700">{alert.message}</p>
                    <p className="mt-1 text-xs text-gray-500">
                      projected {alert.projected_inventory.toFixed(0)} vs {alert.forecast_lead_time_demand.toFixed(0)} forecast ·{" "}
                      {new Date(alert.created_at).toLocaleString()}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => acknowledge(alert.id)}
                    disabled={busyId === alert.id}
                    className="shrink-0 rounded border border-gray-400 bg-white px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                  >
                    {busyId === alert.id ? "Saving…" : "Acknowledge"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <div className="border-t border-gray-200 px-4 py-3">
          <a href="/live" onClick={onClose} className="text-sm font-medium text-brand-700 hover:underline">
            Open Live Operations →
          </a>
        </div>
      </aside>
    </div>
  );
}
