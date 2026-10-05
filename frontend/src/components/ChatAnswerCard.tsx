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
      const inventoryTotal = num(data.total_inventory_units);
      if (total === null && inventoryTotal === null) return null;
      return (
        <div className="mt-2 rounded bg-white/70 p-2 text-xs">
          <div className="mb-1 flex items-center justify-between gap-2">
            {productLink(productId, "/inventory", "View in Inventory")}
            <PinControl productId={productId} />
          </div>
          <dl className="space-y-0.5">
            <Row label={total === null ? "All inventory" : "Total stock"} value={`${(total ?? inventoryTotal ?? 0).toLocaleString()} units`} />
            {num(data.product_count) !== null && <Row label="Products" value={String(data.product_count)} />}
            {num(data.store_count) !== null && <Row label="Stores" value={String(data.store_count)} />}
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
    case "REVENUE_ANALYSIS": {
      const revenue = num(data.net_sales_revenue);
      const grouped = Array.isArray(data.items) ? data.items as Array<Record<string, unknown>> : [];
      if (revenue === null && grouped.length === 0) return null;
      const filters = (data.filters ?? {}) as Record<string, unknown>;
      const scope = [filters.product_id, filters.store_id, filters.category]
        .filter((value): value is string => typeof value === "string").join(" · ");
      return (
        <div className="mt-2 rounded bg-white/70 p-2 text-xs">
          <div className="mb-1">
            <Link to="/sales" className="font-medium text-brand-700 underline-offset-2 hover:underline">
              View in Sales →
            </Link>
          </div>
          <dl className="space-y-0.5">
            {revenue !== null && <Row label="Net sales revenue" value={`$${revenue.toFixed(2)}`} />}
            {num(data.gross_sales_value) !== null && <Row label="Before discounts" value={`$${(data.gross_sales_value as number).toFixed(2)}`} />}
            {scope && <Row label="Filters" value={scope} />}
            {typeof data.daily_records_count === "number" && <Row label="Daily records" value={String(data.daily_records_count)} />}
            {grouped.length > 0 && grouped.slice(0, 5).map((item) => (
              <Row key={String(item.group_value)} label={String(item.group_value)} value={`$${(num(item.net_sales_revenue) ?? 0).toFixed(2)}`} />
            ))}
            <Row label="Measure" value="Revenue, not profit" />
          </dl>
        </div>
      );
    }
    case "STORE_PROFITABILITY": {
      const items = Array.isArray(data.items) ? data.items as Array<Record<string, unknown>> : [];
      if (items.length === 0) return null;
      return (
        <div className="mt-2 rounded bg-white/70 p-2 text-xs">
          <Link to="/sales" className="font-medium text-brand-700 underline-offset-2 hover:underline">Open Store Profit and Loss →</Link>
          <ul className="mt-1 space-y-1">
            {items.slice(0, 5).map((item) => (
              <li key={String(item.store_id)} className="flex justify-between gap-3">
                <span>{String(item.store_id)} · {typeof item.cost_coverage_percent === "number" ? `${item.cost_coverage_percent}% cost data` : "cost data unavailable"}</span>
                <strong className={item.condition === "loss" ? "text-red-700" : item.condition === "profit" ? "text-green-700" : "text-gray-600"}>
                  {typeof item.gross_profit_or_loss === "number" ? `${item.gross_profit_or_loss.toFixed(2)} ${String(item.condition)}` : "unknown"}
                </strong>
              </li>
            ))}
          </ul>
          {typeof data.cost_note === "string" && <p className="mt-1 text-gray-500">{data.cost_note}</p>}
        </div>
      );
    }
    case "FINANCIAL_ANALYSIS": {
      const items = Array.isArray(data.items) ? data.items as Array<Record<string, unknown>> : [];
      if (items.length === 0) return null;
      const groupBy = String(data.group_by ?? "total");
      return (
        <div className="mt-2 rounded bg-white/70 p-2 text-xs">
          <Link to="/sales" className="font-medium text-brand-700 underline-offset-2 hover:underline">Open gross profit report →</Link>
          <ul className="mt-1 space-y-1">
            {items.slice(0, 5).map((item) => {
              const amount = num(item.gross_profit_or_loss);
              const label = String(item.group_value ?? "all sales");
              return (
                <li key={label} className="flex justify-between gap-3">
                  <span>{groupBy === "total" ? "Total" : label} · {num(item.cost_coverage_percent)?.toFixed(0) ?? "0"}% cost coverage</span>
                  <strong className={item.condition === "loss" ? "text-red-700" : item.condition === "profit" ? "text-green-700" : "text-gray-600"}>
                    {amount === null ? "unknown" : `${amount.toFixed(2)} ${String(item.condition ?? "")}`}
                  </strong>
                </li>
              );
            })}
          </ul>
          {typeof data.cost_note === "string" && <p className="mt-1 text-gray-500">{data.cost_note}</p>}
        </div>
      );
    }
    case "LOW_STOCK_FAST_SELLING": {
      const items = Array.isArray(data.items) ? data.items as Array<Record<string, unknown>> : [];
      if (items.length === 0) return null;
      return (
        <div className="mt-2 rounded bg-white/70 p-2 text-xs">
          <Link to="/inventory" className="font-medium text-brand-700 underline-offset-2 hover:underline">Low stock with recent sales →</Link>
          <ul className="mt-1 space-y-0.5">
            {items.slice(0, 5).map((item) => (
              <li key={`${String(item.product_id)}-${String(item.store_id)}`}>
                {String(item.product_id)} at {String(item.store_id)} · {String(item.inventory_level)} on hand · {String(item.units_sold_in_30_days)} sold in the recent window
              </li>
            ))}
          </ul>
        </div>
      );
    }
    case "STOCK_HISTORY": {
      const items = Array.isArray(data.items) ? data.items as Array<Record<string, unknown>> : [];
      if (items.length === 0) return null;
      return (
        <div className="mt-2 rounded bg-white/70 p-2 text-xs">
          <Link to="/inventory" className="font-medium text-brand-700 underline-offset-2 hover:underline">Open inventory →</Link>
          <ul className="mt-1 space-y-0.5">
            {items.slice(0, 5).map((item, index) => (
              <li key={`${String(item.business_date)}-${String(item.product_id)}-${index}`}>
                {String(item.business_date)} · {String(item.product_id)} at {String(item.store_id)} · {String(item.movement_type).toLowerCase().replace(/_/g, " ")} {num(item.quantity_delta)?.toLocaleString() ?? "?"} · {String(item.reason)}
              </li>
            ))}
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
