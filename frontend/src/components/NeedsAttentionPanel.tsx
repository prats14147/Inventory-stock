// frontend/src/components/NeedsAttentionPanel.tsx
//
// "Needs attention today" -- the top of the dashboard (Tier B). Answers one
// question in one place: what is on fire right now, and what do I press?
//
// Every row comes from the single /api/dashboard/summary call, and the figures
// on it are the same ones the Stockout / Reorder pages show. The buttons are
// real navigation, not decoration.

import { Link } from "react-router-dom";
import type { NeedsAttentionItem } from "../types/dashboard";
import type { StockoutAlert } from "../types/live";
import Card from "./Card";
import RiskBadge from "./RiskBadge";
import PinButton from "./PinButton";
import { LoadingState, ErrorState } from "./LoadingError";

interface Props {
  items: NeedsAttentionItem[];
  loading: boolean;
  error: string | null;
  asOfDate: string | null;
  /** Live CRITICAL alerts, which come from the websocket -- not the summary. */
  criticalAlerts?: StockoutAlert[];
}

function shortfall(item: NeedsAttentionItem): number {
  return Math.max(0, item.required_inventory - item.current_inventory);
}

export default function NeedsAttentionPanel({ items, loading, error, asOfDate, criticalAlerts = [] }: Props) {
  if (loading) return <LoadingState label="Checking what needs attention..." />;
  if (error) return <ErrorState message={error} />;

  if (items.length === 0 && criticalAlerts.length === 0) {
    return (
      <Card title="Needs attention today" subtitle={asOfDate ? `As of ${asOfDate}` : undefined}>
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-6 text-center">
          <p className="text-sm font-medium text-green-800">Nothing needs a decision right now.</p>
          <p className="mt-1 text-xs text-green-700">
            Every product covers its forecast demand plus the safety-stock buffer.
          </p>
          <Link
            to="/watchlist"
            className="mt-3 inline-block rounded-lg border border-green-300 bg-white px-3 py-1.5 text-sm font-medium text-green-800 hover:bg-green-100"
          >
            Pin a product to watch it
          </Link>
        </div>
      </Card>
    );
  }

  const totalUnits = items.reduce((sum, i) => sum + i.recommended_reorder_quantity, 0);

  return (
    <Card
      title="Needs attention today"
      subtitle={`${items.length} product${items.length === 1 ? "" : "s"} at medium or high risk${asOfDate ? ` · as of ${asOfDate}` : ""}`}
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-gray-50 px-3 py-2 text-sm">
        <span className="text-gray-600">
          Suggested total order:{" "}
          <span className="font-semibold tabular-nums text-gray-900">{Math.round(totalUnits).toLocaleString()} units</span>
        </span>
        <div className="flex gap-2">
          <Link
            to="/reorder"
            className="rounded-lg bg-brand-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-brand-700"
          >
            Open reorder list
          </Link>
          <Link
            to="/stockout"
            className="rounded-lg border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
          >
            All stockout risk
          </Link>
        </div>
      </div>

      <ul className="divide-y divide-gray-100">
        {criticalAlerts.slice(0, 3).map((alert) => (
          <li key={`live-${alert.id}`} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-gray-900">{alert.product_id}</span>
                <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-800 ring-1 ring-inset ring-red-600/20">
                  <span className="h-1.5 w-1.5 rounded-full bg-red-500" /> Live critical
                </span>
              </div>
              <p className="mt-0.5 text-xs text-gray-500">{alert.message}</p>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <PinButton productId={alert.product_id} />
              <a
                href="#live-operations"
                className="rounded-lg border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
              >
                Handle
              </a>
            </div>
          </li>
        ))}

        {items.map((item) => (
          <li key={item.product_id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-gray-900">{item.product_id}</span>
                <RiskBadge risk={item.risk} />
                <span className="text-xs text-gray-500">
                  short by{" "}
                  <span className="font-semibold tabular-nums text-red-600">
                    {Math.round(shortfall(item)).toLocaleString()}
                  </span>{" "}
                  units
                </span>
              </div>
              <p className="mt-0.5 text-xs text-gray-500">
                On hand {Math.round(item.current_inventory).toLocaleString()} · needs{" "}
                {Math.round(item.required_inventory).toLocaleString()} · order{" "}
                <span className="font-semibold tabular-nums text-brand-700">
                  {Math.round(item.recommended_reorder_quantity).toLocaleString()}
                </span>
              </p>
            </div>

            <div className="flex shrink-0 items-center gap-1.5">
              <PinButton productId={item.product_id} />
              <Link
                to={`/reorder?product=${item.product_id}`}
                className="rounded-lg border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
              >
                Reorder
              </Link>
              <Link
                to={`/forecast?product=${item.product_id}`}
                className="rounded-lg border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
              >
                Why?
              </Link>
            </div>
          </li>
        ))}
      </ul>

      {items.length >= 8 && (
        <p className="mt-2 text-xs text-gray-500">
          Showing the 8 most urgent.{" "}
          <Link to="/stockout" className="text-brand-700 hover:underline">
            See all at-risk products
          </Link>
          .
        </p>
      )}
    </Card>
  );
}