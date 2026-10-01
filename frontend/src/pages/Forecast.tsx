// frontend/src/pages/Forecast.tsx

import { useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { useApi } from "../hooks/useApi";
import { getProducts, getForecast } from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";

export default function Forecast() {
  const products = useApi(() => getProducts(), []);
  const [productId, setProductId] = useState("");
  const [horizon, setHorizon] = useState(14);

  const forecast = useApi(() => (productId ? getForecast(productId, horizon) : Promise.resolve(null)), [
    productId,
    horizon,
  ]);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Demand Forecast</h1>

      <div className="flex flex-wrap items-end gap-4 rounded-lg border bg-white p-4 shadow-sm">
        <label className="flex flex-col text-sm">
          Product
          <select
            className="mt-1 rounded-md border px-3 py-1.5"
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
          >
            <option value="">Select a product...</option>
            {products.data?.product_ids.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col text-sm">
          Forecast horizon
          <select className="mt-1 rounded-md border px-3 py-1.5" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
          </select>
        </label>
      </div>

      {!productId && <p className="text-gray-500">Select a product to see its demand forecast.</p>}
      {productId && forecast.loading && <LoadingState label="Forecasting..." />}
      {productId && forecast.error && <ErrorState message={forecast.error} />}

      {forecast.data && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-lg border bg-white p-4 shadow-sm">
              <p className="text-sm text-gray-500">Total forecast demand</p>
              <p className="mt-1 text-2xl font-semibold">{forecast.data.forecast_total_units.toFixed(0)} units</p>
              <p className="mt-1 text-xs text-gray-400">by {forecast.data.target_date}</p>
            </div>
            <div className="rounded-lg border bg-white p-4 shadow-sm">
              <p className="text-sm text-gray-500">Model horizon used</p>
              <p className="mt-1 text-2xl font-semibold">{forecast.data.model_horizon_days} days</p>
              {forecast.data.model_horizon_days !== forecast.data.requested_horizon_days && (
                <p className="mt-1 text-xs text-amber-600">
                  Nearest trained model used (requested {forecast.data.requested_horizon_days} days)
                </p>
              )}
            </div>
            <div className="rounded-lg border bg-white p-4 shadow-sm">
              <p className="text-sm text-gray-500">Model test MAE</p>
              <p className="mt-1 text-2xl font-semibold">{forecast.data.model_test_mae.toFixed(1)}</p>
              <p className="mt-1 text-xs text-gray-400">lower is better; see docs/limitations.md</p>
            </div>
          </div>

          <div className="rounded-lg border bg-white p-4 shadow-sm">
            <h2 className="mb-3 text-sm font-medium text-gray-600">Forecast by Store</h2>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={forecast.data.per_store}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="store_id" fontSize={12} />
                <YAxis fontSize={12} />
                <Tooltip />
                <Bar dataKey="forecast_units" fill="#2563eb" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
