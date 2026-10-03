// frontend/src/components/AlertDigestPanel.tsx
//
// "What happened today" in one card: the day's alert counts plus the products
// that fired, worst-first. Read-only -- acknowledging an alert still happens
// in the live alerts panel, so there is exactly one place that mutates state.

import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { getAlertDigest } from "../services/api";
import Card from "./Card";
import StatCard from "./StatCard";
import EmptyState from "./EmptyState";
import { LoadingState, ErrorState } from "./LoadingError";

function SeverityPill({ severity }: { severity: "CRITICAL" | "WARNING" }) {
  const critical = severity === "CRITICAL";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${
        critical
          ? "bg-red-100 text-red-800 ring-red-600/20"
          : "bg-amber-100 text-amber-800 ring-amber-600/20"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${critical ? "bg-red-500" : "bg-amber-500"}`} />
      {critical ? "Critical" : "Warning"}
    </span>
  );
}

export default function AlertDigestPanel() {
  const { data, loading, error } = useApi(() => getAlertDigest(), []);

  if (loading) return <LoadingState label="Building today's digest..." />;
  if (error) return <ErrorState message={error} />;
  if (!data) return null;

  const quiet = data.total_alerts === 0;

  return (
    <Card
      title="Today's alert digest"
      subtitle={`${data.date} (UTC) · ${data.products_affected} product${data.products_affected === 1 ? "" : "s"} affected`}
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Alerts" value={data.total_alerts} />
        <StatCard
          label="Critical"
          value={data.critical_alerts}
          accent={data.critical_alerts > 0 ? "danger" : "success"}
        />
        <StatCard
          label="Still open"
          value={data.open_alerts}
          hint={`${data.acknowledged_alerts} handled`}
          accent={data.open_alerts > 0 ? "warning" : "success"}
        />
        <StatCard label="Products hit" value={data.products_affected} />
      </div>

      {quiet ? (
        <div className="mt-4">
          <EmptyState
            title="Nothing fired today."
            hint="No stockout alerts have been raised yet for this UTC day. Start the live stream on the dashboard to generate some."
          />
        </div>
      ) : (
        <ul className="mt-4 divide-y divide-gray-100">
          {data.products.slice(0, 8).map((p) => (
            <li key={p.product_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <SeverityPill severity={p.worst_severity} />
                <span className="font-medium text-gray-900">{p.product_id}</span>
                <span className="text-xs text-gray-500">
                  {p.alert_count} alert{p.alert_count === 1 ? "" : "s"}
                  {p.open_count > 0 ? ` · ${p.open_count} open` : " · all handled"}
                </span>
              </div>
              <div className="flex gap-3 text-xs font-medium">
                <Link to={`/stockout?product=${p.product_id}`} className="text-brand-700 hover:underline">
                  Risk →
                </Link>
                <Link to={`/inventory?product=${p.product_id}`} className="text-brand-700 hover:underline">
                  Stock →
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}

      {data.products.length > 8 && (
        <p className="mt-3 text-xs text-gray-500">
          Showing the 8 worst of {data.products.length} affected products.
        </p>
      )}
    </Card>
  );
}