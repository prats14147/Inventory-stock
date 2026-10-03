// frontend/src/components/ChatAnswerCard.tsx
//
// Renders the verified `data` payload of a chat answer as a small card with
// links into the matching dashboard page. Text stays the message; the card
// is additive -- if the payload shape is unexpected it renders nothing.

import { Link } from "react-router-dom";
import type { ChatResponse } from "../types/chat";
import RiskBadge from "./RiskBadge";
import PinButton from "./PinButton";
import type { RiskLevel } from "../types/stockout";

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Deep links carry ?product= so the target page opens already filtered. */
function productLink(productId: string | null, to: string, label: string) {
  if (!productId) return null;
  const href = to.includes("?") ? `${to}&product=${encodeURIComponent(productId)}` : `${to}?product=${encodeURIComponent(productId)}`;
  return (
    <Link to={href} className="font-medium text-brand-700 underline-offset-2 hover:underline">
      {label}: {productId} →
    </Link>
  );
}

/** A pin toggle that sits inline with a card's links. */
function PinControl({ productId }: { productId: string | null }) {
  if (!productId) return null;
  return <PinButton productId={productId} />;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-gray-500">{label}</dt>
      <dd className="font-medium text-gray-800">{value}</dd>
    </div>
  );
}

export default function ChatAnswerCard({ response }: { response: ChatResponse }) {
  const data = (response.data ?? {}) as Record<string, unknown>;
  const productId = typeof response.entities.product_id === "string" ? response.entities.product_id : null;

  switch (response.intent) {
    case "CURRENT_STOCK": {
      const total = num(data.total_inventory);
      if (total === null) return null;
      return (
        <div className="mt-2 rounded bg-white/70 p-2 text-xs">
          <div className="mb-1 flex items-center justify-between gap-2">
            {productLink(productId, "/inventory", "View in Inventory")}
            <PinControl productId={productId} />
          </div>
          <dl className="space-y-0.5">
            <Row label="Total stock" value={`${total.toFixed(0)} units`} />
            {typeof data.as_of_date === "string" && <Row label="As of" value={data.as_of_date} />}
          </dl>
        </div>
      );
    }
    case "STOCKOUT_RISK": {
      const risk = typeof data.risk === "string" ? data.risk : null;
      if (!risk) return null;
      return (
        <div className="mt-2 rounded bg-white/70 p-2 text-xs">
          <div className="mb-1 flex items-center justify-between gap-2">
            <RiskBadge risk={risk as RiskLevel} />
            {productLink(productId, "/stockout", "Risk details")}
          </div>
          <div className="mb-1 flex justify-end">
            <PinControl productId={productId} />
          </div>
          <dl className="space-y-0.5">
            {num(data.current_inventory) !== null && (
              <Row label="Current inventory" value={`${(data.current_inventory as number).toFixed(0)}`} />
            )}
            {num(data.required_inventory) !== null && (
              <Row label="Required" value={`${(data.required_inventory as number).toFixed(1)}`} />
            )}
          </dl>
        </div>
      );
    }
    case "REORDER_RECOMMENDATION": {
      const qty = num(data.recommended_reorder_quantity);
      if (qty === null) return null;
      return (
        <div className="mt-2 rounded bg-white/70 p-2 text-xs">
          <div className="mb-1 flex items-center justify-between gap-2">
            {productLink(productId, "/reorder", "View in Reorder")}
            <PinControl productId={productId} />
          </div>
          <dl className="space-y-0.5">
            <Row label="Recommended order" value={`${qty.toFixed(0)} units`} />
            {num(data.current_inventory) !== null && (
              <Row label="On hand" value={`${(data.current_inventory as number).toFixed(0)}`} />
            )}
          </dl>
        </div>
      );
    }
    case "DEMAND_FORECAST": {
      const total = num(data.forecast_total_units);
      if (total === null) return null;
      return (
        <div className="mt-2 rounded bg-white/70 p-2 text-xs">
          <div className="mb-1 flex items-center justify-between gap-2">
            {productLink(productId, "/forecast", "Open forecast")}
            <PinControl productId={productId} />
          </div>
          <dl className="space-y-0.5">
            <Row label="Forecast demand" value={`${total.toFixed(0)} units`} />
            {typeof data.target_date === "string" && <Row label="By" value={data.target_date} />}
          </dl>
        </div>
      );
    }
    case "TOP_SELLING":
    case "BOTTOM_SELLING": {
      const products = Array.isArray(data.products) ? data.products.slice(0, 3) : [];
      if (products.length === 0) return null;
      return (
        <div className="mt-2 rounded bg-white/70 p-2 text-xs">
          <div className="mb-1">
            <Link to="/sales" className="font-medium text-brand-700 underline-offset-2 hover:underline">
              View in Sales →
            </Link>
          </div>
          <ul className="space-y-0.5 text-gray-700">
            {products.map((p) => {
              const row = p as Record<string, unknown>;
              return (
                <li key={String(row.product_id)}>
                  {String(row.product_id)} — {num(row.total_units_sold)?.toFixed(0) ?? "?"} units
                </li>
              );
            })}
          </ul>
        </div>
      );
    }
    case "LOW_STOCK": {
      const count = num(data.count);
      if (count === null) return null;
      return (
        <div className="mt-2 rounded bg-white/70 p-2 text-xs">
          <Link to="/inventory" className="font-medium text-brand-700 underline-offset-2 hover:underline">
            {count.toFixed(0)} low-stock combinations — view in Inventory →
          </Link>
        </div>
      );
    }
    default:
      return null;
  }
}
