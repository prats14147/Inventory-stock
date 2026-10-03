// frontend/src/components/LiveAlertsPanel.tsx
//
// Proactive stockout alerts. Every number shown comes from the alert record
// the backend computed (see app/services/simulator_service.py) -- the UI
// renders it, it never derives or guesses one.

import type { StockoutAlert } from "../types/live";

const severityStyles: Record<StockoutAlert["severity"], string> = {
  CRITICAL: "bg-red-100 text-red-800 border-red-200",
  WARNING: "bg-amber-100 text-amber-800 border-amber-200",
};

interface LiveAlertsPanelProps {
  alerts: StockoutAlert[];
  onAcknowledge: (alertId: number) => Promise<void>;
  busyAlertId?: number | null;
}

export default function LiveAlertsPanel({ alerts, onAcknowledge, busyAlertId }: LiveAlertsPanelProps) {
  if (alerts.length === 0) {
    return (
      <p className="rounded border border-dashed border-gray-300 p-4 text-sm text-gray-500">
        No open alerts. Start the simulator to generate live traffic.
      </p>
    );
  }

  return (
    <ul className="space-y-3">
      {alerts.map((alert) => (
        <li key={alert.id} className={`rounded border p-3 ${severityStyles[alert.severity]}`}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold">
                {alert.severity} · {alert.product_id}
              </p>
              <p className="mt-1 text-sm">{alert.message}</p>
              <p className="mt-2 text-xs opacity-80">
                projected {alert.projected_inventory.toFixed(0)} units vs {alert.forecast_lead_time_demand.toFixed(0)}{" "}
                forecast for {alert.lead_time_days}-day lead time · detected {new Date(alert.created_at).toLocaleTimeString()}
              </p>
            </div>
            <button
              type="button"
              onClick={() => onAcknowledge(alert.id)}
              disabled={busyAlertId === alert.id}
              className="shrink-0 rounded border border-current px-2 py-1 text-xs font-medium disabled:opacity-50"
            >
              {busyAlertId === alert.id ? "Saving..." : "Acknowledge"}
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
