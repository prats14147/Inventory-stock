// frontend/src/pages/Reorder.tsx

import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { getReorderList } from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import StatCard from "../components/StatCard";
import PinButton from "../components/PinButton";
import { downloadCsv, toCsv } from "../lib/csv";

export default function Reorder() {
  const [onlyNeeded, setOnlyNeeded] = useState(true);
  const { data, loading, error } = useApi(() => getReorderList(onlyNeeded), [onlyNeeded]);
  const totalQty = (data ?? []).reduce((sum, r) => sum + r.recommended_reorder_quantity, 0);

  // Exports exactly what the table shows, so the file and the screen can never
  // disagree about which filter was applied.
  function exportCsv() {
    if (!data || data.length === 0) return;
    const headers = [
      "Product",
      "As of date",
      "Current inventory",
      "Forecast lead-time demand",
      "Safety stock",
      "Recommended order qty",
    ];
    const rows = data.map((r) => [
      r.product_id,
      r.as_of_date,
      r.current_inventory.toFixed(0),
      r.forecast_lead_time_demand.toFixed(1),
      r.safety_stock.toFixed(1),
      r.recommended_reorder_quantity.toFixed(0),
    ]);
    const scope = onlyNeeded ? "needing-reorder" : "all-products";
    downloadCsv(`reorder-${scope}-${new Date().toISOString().slice(0, 10)}.csv`, toCsv(headers, rows));
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Reorder Recommendations"
        subtitle={
          data && data.length > 0
            ? `${data.length} product${data.length === 1 ? "" : "s"} need reordering · ${totalQty.toFixed(0)} units total.`
            : "Order quantities from forecast demand plus safety stock, minus what's on hand."
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-600 shadow-sm">
              <input type="checkbox" checked={onlyNeeded} onChange={(e) => setOnlyNeeded(e.target.checked)} className="accent-brand-600" />
              Only show products that need reordering
            </label>
            <button
              type="button"
              onClick={exportCsv}
              disabled={!data || data.length === 0}
              className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Export CSV
            </button>
          </div>
        }
      />

      {!loading && !error && (data ?? []).length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard label="Products to reorder" value={data?.length ?? 0} accent="warning" />
          <StatCard label="Total units to order" value={totalQty.toFixed(0)} hint="Sum of recommended quantities" accent="info" />
          <StatCard
            label="Largest single order"
            value={Math.max(...(data ?? []).map((r) => r.recommended_reorder_quantity)).toFixed(0)}
            hint={(data ?? []).sort((a, b) => b.recommended_reorder_quantity - a.recommended_reorder_quantity)[0]?.product_id ?? ""}
          />
        </div>
      )}

      {loading && <LoadingState label="Calculating reorder recommendations..." />}
      {error && <ErrorState message={error} />}

      {!loading && !error && (
        <Card>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  {["Product", "Current Inventory", "Expected Demand", "Safety Stock", "Recommended Order Qty", ""].map(
                    (h) => (
                      <th key={h} className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {(data ?? []).map((r) => (
                  <tr key={r.product_id} className="transition-colors hover:bg-brand-50/50">
                    <td className="whitespace-nowrap px-4 py-2 font-medium text-gray-900">{r.product_id}</td>
                    <td className="whitespace-nowrap px-4 py-2 tabular-nums text-gray-600">{r.current_inventory.toFixed(0)}</td>
                    <td className="whitespace-nowrap px-4 py-2 tabular-nums text-gray-600">{r.forecast_lead_time_demand.toFixed(1)}</td>
                    <td className="whitespace-nowrap px-4 py-2 tabular-nums text-gray-600">{r.safety_stock.toFixed(1)}</td>
                    <td className="whitespace-nowrap px-4 py-2 tabular-nums font-semibold text-brand-700">
                      {r.recommended_reorder_quantity.toFixed(0)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <PinButton productId={r.product_id} />
                        <a href={`/forecast?product=${r.product_id}`} className="text-xs font-medium text-brand-700 hover:underline">
                          Forecast →
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(data ?? []).length === 0 && (
            <div className="mt-3">
              <EmptyState
                title="Nothing needs reordering."
                hint="Every product covers its forecast demand plus safety stock. Uncheck the filter to see all products."
              />
            </div>
          )}
        </Card>
      )}

      <p className="text-xs text-gray-400">
        Lead time and safety-stock assumptions are documented in docs/limitations.md — this dataset has no real
        supplier lead time, so a configurable default is used and disclosed on every calculation.
      </p>
    </div>
  );
}
