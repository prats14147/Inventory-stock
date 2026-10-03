// frontend/src/pages/Forecast.tsx

import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { useApi } from "../hooks/useApi";
import { getProducts, getForecast } from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import StatCard from "../components/StatCard";
import EmptyState from "../components/EmptyState";
import { useSearchParams } from "react-router-dom";

export default function Forecast() {
  const products = useApi(() => getProducts(), []);
  const [searchParams] = useSearchParams();
  const linkedProduct = searchParams.get("product") ?? "";
  const [productId, setProductId] = useState(linkedProduct);
  const [horizon, setHorizon] = useState(14);

  // A chat answer card can deep-link here (?product=P0001) -- adopt it once
  // the product list has loaded and the id is real.
  useEffect(() => {
    if (linkedProduct && !productId && (products.data?.product_ids ?? []).includes(linkedProduct)) {
      setProductId(linkedProduct);
    }
  }, [linkedProduct, productId, products.data]);

  const forecast = useApi(() => (productId ? getForecast(productId, horizon) : Promise.resolve(null)), [
    productId,
    horizon,
  ]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Demand Forecast"
        subtitle="XGBoost forecast per product, broken down by store. Pick a product to see expected demand."
      />

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col text-sm font-medium text-gray-700">
            Product
            <select
              className="mt-1 rounded-lg border border-gray-300 bg-white px-3 py-1.5 shadow-sm focus:border-brand-500 focus:outline-none"
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

          <label className="flex flex-col text-sm font-medium text-gray-700">
            Forecast horizon
            <select
              className="mt-1 rounded-lg border border-gray-300 bg-white px-3 py-1.5 shadow-sm focus:border-brand-500 focus:outline-none"
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
            >
              <option value={7}>7 days</option>
              <option value={14}>14 days</option>
            </select>
          </label>
        </div>
      </Card>

      {!productId && (
        <EmptyState
          title="Select a product to see its demand forecast."
          hint="Forecasts come from the trained XGBoost model — try P0001 or any product you asked the chatbot about."
        />
      )}
      {productId && forecast.loading && <LoadingState label="Forecasting..." />}
      {productId && forecast.error && <ErrorState message={forecast.error} />}

      {forecast.data && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard
              label="Total forecast demand"
              value={`${forecast.data.forecast_total_units.toFixed(0)} units`}
              hint={`by ${forecast.data.target_date}`}
              accent="info"
            />
            <StatCard
              label="Model horizon used"
              value={`${forecast.data.model_horizon_days} days`}
              hint={
                forecast.data.model_horizon_days !== forecast.data.requested_horizon_days
                  ? `Nearest trained model (requested ${forecast.data.requested_horizon_days} days)`
                  : "Matches your request"
              }
              accent={forecast.data.model_horizon_days !== forecast.data.requested_horizon_days ? "warning" : "default"}
            />
            <StatCard
              label="Model test MAE"
              value={forecast.data.model_test_mae.toFixed(1)}
              hint="Lower is better; see docs/limitations.md"
            />
          </div>

          <Card title="Forecast by Store" subtitle={`Expected demand for ${forecast.data.product_id}`}>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={forecast.data.per_store}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="store_id" fontSize={12} tickLine={false} axisLine={{ stroke: "#e5e7eb" }} />
                <YAxis fontSize={12} tickLine={false} axisLine={false} tickFormatter={(v: number) => v.toLocaleString()} />
                <Tooltip formatter={(v) => [`${Number(v).toLocaleString()} units`, "Forecast"]} cursor={{ fill: "#eff6ff" }} />
                <Bar dataKey="forecast_units" fill="#2563eb" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>
      )}
    </div>
  );
}
