// frontend/src/pages/Stockout.tsx

import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { getStockoutRiskList } from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";
import RiskBadge from "../components/RiskBadge";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import PinButton from "../components/PinButton";

export default function Stockout() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlProduct = searchParams.get("product") ?? "";
  const [onlyAtRisk, setOnlyAtRisk] = useState(false);
  const { data, loading, error } = useApi(() => getStockoutRiskList(onlyAtRisk), [onlyAtRisk]);
  const highCount = (data ?? []).filter((item) => item.risk === "HIGH").length;
  const mediumCount = (data ?? []).filter((item) => item.risk === "MEDIUM").length;

  // Deep link (?product=P0001) narrows the grid to that product, so the watchlist
  // and chat answer cards land on the exact card the user asked about.
  const visible = urlProduct ? (data ?? []).filter((item) => item.product_id === urlProduct) : (data ?? []);

  function clearProduct() {
    const params = new URLSearchParams(searchParams);
    params.delete("product");
    setSearchParams(params, { replace: true });
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Stockout Risk"
        subtitle={
          data
            ? `${highCount} high risk · ${mediumCount} medium risk across ${data.length} products.`
            : "Forecast demand vs on-hand inventory over the lead time, with safety stock."
        }
        actions={
          <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-600 shadow-sm">
            <input type="checkbox" checked={onlyAtRisk} onChange={(e) => setOnlyAtRisk(e.target.checked)} className="accent-brand-600" />
            Only show at-risk products
          </label>
        }
      />

      {urlProduct && !loading && !error && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-brand-800">
          <span>
            Showing <span className="font-semibold">{urlProduct}</span> only.
          </span>
          <button
            type="button"
            onClick={clearProduct}
            className="rounded-lg border border-brand-300 bg-white px-2 py-0.5 text-xs font-medium text-brand-700 hover:bg-brand-100"
          >
            Show all products
          </button>
        </div>
      )}

      {loading && <LoadingState label="Calculating stockout risk..." />}
      {error && <ErrorState message={error} />}

      {!loading && !error && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {visible.map((item) => (
              <Card
                key={item.product_id}
                className={
                  item.risk === "HIGH"
                    ? "border-l-4 border-l-red-500"
                    : item.risk === "MEDIUM"
                      ? "border-l-4 border-l-amber-500"
                      : "border-l-4 border-l-green-500"
                }
              >
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-semibold text-gray-900">{item.product_id}</span>
                  <div className="flex items-center gap-2">
                    <RiskBadge risk={item.risk} />
                    <PinButton productId={item.product_id} />
                  </div>
                </div>
                <dl className="space-y-1 text-sm text-gray-600">
                  <div className="flex justify-between">
                    <dt>Current inventory</dt>
                    <dd className="tabular-nums font-medium text-gray-900">{item.current_inventory.toFixed(0)}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Forecast demand ({item.lead_time_days}d lead time)</dt>
                    <dd className="tabular-nums">{item.forecast_lead_time_demand.toFixed(1)}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Safety stock</dt>
                    <dd className="tabular-nums">{item.safety_stock.toFixed(1)}</dd>
                  </div>
                  <div className="flex justify-between border-t border-gray-100 pt-1 font-medium text-gray-800">
                    <dt>Required inventory</dt>
                    <dd className="tabular-nums">{item.required_inventory.toFixed(1)}</dd>
                  </div>
                </dl>
                <p className="mt-3 border-t border-gray-100 pt-2 text-xs text-gray-500">{item.reason}</p>
                <div className="mt-2 flex gap-3 text-xs font-medium">
                  <a href={`/reorder`} className="text-brand-700 hover:underline">
                    Reorder →
                  </a>
                  <a href={`/forecast?product=${item.product_id}`} className="text-brand-700 hover:underline">
                    Forecast →
                  </a>
                </div>
              </Card>
            ))}
          </div>
          {visible.length === 0 && (
            <EmptyState
              title={
                urlProduct
                  ? `No risk record for ${urlProduct}.`
                  : onlyAtRisk
                    ? "No at-risk products right now."
                    : "No products match this filter."
              }
              hint={
                urlProduct
                  ? "Clear the product filter to see every product."
                  : "Uncheck the at-risk filter to see every product, or check the Reorder page for order quantities."
              }
            />
          )}
        </>
      )}
    </div>
  );
}
