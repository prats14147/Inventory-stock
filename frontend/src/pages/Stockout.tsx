// frontend/src/pages/Stockout.tsx

import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { getStockoutRiskList } from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";
import RiskBadge from "../components/RiskBadge";

export default function Stockout() {
  const [onlyAtRisk, setOnlyAtRisk] = useState(false);
  const { data, loading, error } = useApi(() => getStockoutRiskList(onlyAtRisk), [onlyAtRisk]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Stockout Risk</h1>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          <input type="checkbox" checked={onlyAtRisk} onChange={(e) => setOnlyAtRisk(e.target.checked)} />
          Only show at-risk products
        </label>
      </div>

      {loading && <LoadingState label="Calculating stockout risk..." />}
      {error && <ErrorState message={error} />}

      {!loading && !error && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {(data ?? []).map((item) => (
            <div key={item.product_id} className="rounded-lg border bg-white p-4 shadow-sm">
              <div className="mb-2 flex items-center justify-between">
                <span className="font-semibold">{item.product_id}</span>
                <RiskBadge risk={item.risk} />
              </div>
              <dl className="space-y-1 text-sm text-gray-600">
                <div className="flex justify-between">
                  <dt>Current inventory</dt>
                  <dd>{item.current_inventory.toFixed(0)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt>Forecast demand ({item.lead_time_days}d lead time)</dt>
                  <dd>{item.forecast_lead_time_demand.toFixed(1)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt>Safety stock</dt>
                  <dd>{item.safety_stock.toFixed(1)}</dd>
                </div>
                <div className="flex justify-between font-medium text-gray-800">
                  <dt>Required inventory</dt>
                  <dd>{item.required_inventory.toFixed(1)}</dd>
                </div>
              </dl>
              <p className="mt-3 text-xs text-gray-500">{item.reason}</p>
            </div>
          ))}
          {(data ?? []).length === 0 && (
            <p className="col-span-full text-center text-gray-500">No products match this filter.</p>
          )}
        </div>
      )}
    </div>
  );
}
