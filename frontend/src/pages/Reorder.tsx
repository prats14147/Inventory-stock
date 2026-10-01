// frontend/src/pages/Reorder.tsx

import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { getReorderList } from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";

export default function Reorder() {
  const [onlyNeeded, setOnlyNeeded] = useState(true);
  const { data, loading, error } = useApi(() => getReorderList(onlyNeeded), [onlyNeeded]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Reorder Recommendations</h1>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          <input type="checkbox" checked={onlyNeeded} onChange={(e) => setOnlyNeeded(e.target.checked)} />
          Only show products that need reordering
        </label>
      </div>

      {loading && <LoadingState label="Calculating reorder recommendations..." />}
      {error && <ErrorState message={error} />}

      {!loading && !error && (
        <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                {["Product", "Current Inventory", "Expected Demand", "Safety Stock", "Recommended Order Qty"].map(
                  (h) => (
                    <th key={h} className="px-4 py-2 text-left font-medium text-gray-500">
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(data ?? []).map((r) => (
                <tr key={r.product_id}>
                  <td className="px-4 py-2 font-medium">{r.product_id}</td>
                  <td className="px-4 py-2">{r.current_inventory.toFixed(0)}</td>
                  <td className="px-4 py-2">{r.forecast_lead_time_demand.toFixed(1)}</td>
                  <td className="px-4 py-2">{r.safety_stock.toFixed(1)}</td>
                  <td className="px-4 py-2 font-semibold text-brand-700">
                    {r.recommended_reorder_quantity.toFixed(0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(data ?? []).length === 0 && <p className="p-4 text-center text-gray-500">Nothing needs reordering.</p>}
        </div>
      )}

      <p className="text-xs text-gray-400">
        Lead time and safety-stock assumptions are documented in docs/limitations.md — this dataset has no real
        supplier lead time, so a configurable default is used and disclosed on every calculation.
      </p>
    </div>
  );
}
