// frontend/src/pages/Forecast.tsx

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

import { useApi } from "../hooks/useApi";
import { getForecast, getProducts } from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import StatCard from "../components/StatCard";
import EmptyState from "../components/EmptyState";

export default function Forecast() {
  const products = useApi(() => getProducts(), []);

  const [searchParams] = useSearchParams();
  const linkedProduct = searchParams.get("product") ?? "";

  const [productId, setProductId] = useState(linkedProduct);
  const [horizon, setHorizon] = useState(14);

  // A chat answer card can deep-link here (?product=P0001).
  // Adopt it once the product list has loaded and the id is real.
  useEffect(() => {
    if (
      linkedProduct &&
      !productId &&
      (products.data?.products ?? []).some(
        (product) => product.product_id === linkedProduct
      )
    ) {
      setProductId(linkedProduct);
    }
  }, [linkedProduct, productId, products.data]);

  const forecast = useApi(
    () =>
      productId
        ? getForecast(productId, horizon)
        : Promise.resolve(null),
    [productId, horizon]
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Demand Forecast"
        subtitle="XGBoost forecast per product, broken down by store. Pick a product to see expected demand."
      />

      <div
        className="rounded-xl border border-amber-300 bg-amber-50 p-4 shadow-sm text-amber-900"
        role="alert"
      >
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex-shrink-0 rounded-lg bg-amber-200 p-1.5 text-amber-800">
            <svg
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>

          <div className="space-y-1.5 text-sm">
            <h3 className="flex items-center gap-2 font-semibold text-amber-950">
              <span>Synthetic Dataset Notice</span>
              <span className="rounded bg-amber-200 px-2 py-0.5 text-xs font-medium text-amber-900">
                Baseline +~5% Only
              </span>
            </h3>

            <p className="leading-relaxed text-amber-800">
              Demand forecasts are generated using an XGBoost model trained
              strictly on the{" "}
              <strong>synthetic sample dataset (2022–2024)</strong>.
              According to project documentation, this model outperforms its
              naive 7-day moving average baseline by only{" "}
              <strong>approximately 5%</strong> (MAE ~88.5 vs baseline ~93.4)
              with high sMAPE (~72–74%), due to weak price/promotion signals
              in the synthetic generating process.
            </p>

            <p className="text-xs text-amber-700">
              <strong>Data Isolation:</strong> Genuine sales entered manually (
              <code className="rounded bg-amber-100 px-1 py-0.5 font-mono text-amber-900">
                Real · Manual
              </code>
              ) or imported via CSV (
              <code className="rounded bg-amber-100 px-1 py-0.5 font-mono text-amber-900">
                Real · CSV Import
              </code>
              ) are stored separately and are not mixed into this synthetic
              pipeline to prevent misleading forecasts.
            </p>
          </div>
        </div>
      </div>

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

              {products.data?.products.map((product) => (
                <option
                  key={product.product_id}
                  value={product.product_id}
                >
                  {product.product_id} — {product.name} ({product.sku})
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

      {productId && forecast.loading && (
        <LoadingState label="Forecasting..." />
      )}

      {productId && forecast.error && (
        <ErrorState message={forecast.error} />
      )}

      {forecast.data && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Total forecast demand"
              value={`${forecast.data.forecast_total_units.toFixed(0)} units`}
              hint={`by ${forecast.data.target_date}`}
              accent="info"
            />

            <StatCard
              label="Data source"
              value="Synthetic 2022-2024"
              hint="Pure sample dataset (Real sales excluded)"
              accent="warning"
            />

            <StatCard
              label="Model test MAE"
              value={forecast.data.model_test_mae.toFixed(1)}
              hint={`Outperforms baseline by ~${
                forecast.data.baseline_improvement_pct ?? 5
              }%`}
            />

            <StatCard
              label="Model horizon used"
              value={`${forecast.data.model_horizon_days} days`}
              hint={
                forecast.data.model_horizon_days !==
                forecast.data.requested_horizon_days
                  ? `Nearest trained model (requested ${forecast.data.requested_horizon_days} days)`
                  : "Matches your request"
              }
              accent={
                forecast.data.model_horizon_days !==
                forecast.data.requested_horizon_days
                  ? "warning"
                  : "default"
              }
            />
          </div>

          <Card
            title="Forecast by Store"
            subtitle={`Expected demand for ${forecast.data.product_id}`}
          >
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={forecast.data.per_store}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#e5e7eb"
                />

                <XAxis
                  dataKey="store_id"
                  fontSize={12}
                  tickLine={false}
                  axisLine={{ stroke: "#e5e7eb" }}
                />

                <YAxis
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) =>
                    v.toLocaleString()
                  }
                />

                <Tooltip
                  formatter={(v) => [
                    `${Number(v).toLocaleString()} units`,
                    "Forecast",
                  ]}
                  cursor={{ fill: "#eff6ff" }}
                />

                <Bar
                  dataKey="forecast_units"
                  fill="#2563eb"
                  radius={[6, 6, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>
      )}
    </div>
  );
}
