// frontend/src/pages/Forecast.tsx

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useApi } from "../hooks/useApi";
import {
  getForecast,
  getProducts,
  getSalesTrend,
} from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import StatCard from "../components/StatCard";
import EmptyState from "../components/EmptyState";

const HISTORY_POINTS = 30;

interface ForecastChartRow {
  date: string;
  label: string;
  historical_units: number | null;
  forecast_units: number | null;
  forecast7_units: number | null;
  forecast14_units: number | null;
  isForecast: boolean;
}

function formatDateLabel(value: string) {
  const date = new Date(`${value}T00:00:00`);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

export default function Forecast() {
  const products = useApi(() => getProducts(), []);

  const [searchParams] = useSearchParams();
  const linkedProduct = searchParams.get("product") ?? "";

  const [productId, setProductId] = useState(linkedProduct);
  const [compareId, setCompareId] = useState("");
  const [compareOn, setCompareOn] = useState(false);
  const [horizon, setHorizon] = useState(14);

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

  // Fetch both supported model horizons so the graph can show
  // the 7-day and 14-day outputs together.
  const forecast7 = useApi(
    () =>
      productId
        ? getForecast(productId, 7)
        : Promise.resolve(null),
    [productId]
  );

  const forecast14 = useApi(
    () =>
      productId
        ? getForecast(productId, 14)
        : Promise.resolve(null),
    [productId]
  );

  // Historical demand is filtered to the synthetic dataset so the
  // chart uses the same data source as the forecasting models.
  const history = useApi(
    () =>
      productId
        ? getSalesTrend({
            granularity: "daily",
            product_id: productId,
            source: "Sample Data",
          })
        : Promise.resolve(null),
    [productId]
  );

  const selectedForecast =
    horizon === 7 ? forecast7.data : forecast14.data;

  // Side-by-side compare mode: second product at the selected horizon.
  const compareForecast = useApi(
    () =>
      compareOn && compareId && compareId !== productId
        ? getForecast(compareId, horizon)
        : Promise.resolve(null),
    [compareOn, compareId, productId, horizon]
  );

  const compareRows = (() => {
    const leftData = selectedForecast;
    const rightData = compareForecast.data;
    if (!leftData || !rightData) return [];
    const left = new Map(leftData.per_store.map((r) => [r.store_id, r.forecast_units]));
    const right = new Map(rightData.per_store.map((r) => [r.store_id, r.forecast_units]));
    const stores = Array.from(new Set([...left.keys(), ...right.keys()])).sort();
    return stores.map((store_id) => ({
      store_id,
      [leftData.product_id]: Number((left.get(store_id) ?? 0).toFixed(1)),
      [rightData.product_id]: Number((right.get(store_id) ?? 0).toFixed(1)),
    }));
  })();

  const forecastError =
    forecast7.error ?? forecast14.error ?? history.error;

  const forecastLoading = Boolean(
    forecast7.loading ||
      forecast14.loading ||
      history.loading
  );

  const chartData = useMemo(() => {
    const historicalPoints =
      history.data?.points ?? [];

    const recentHistory = historicalPoints.slice(
      -HISTORY_POINTS
    );

    if (recentHistory.length === 0) {
      return [];
    }

    const rows: ForecastChartRow[] = recentHistory.map((point) => ({
      date: point.period,
      label: formatDateLabel(point.period),
      historical_units: point.total_units_sold,
      forecast_units: null as number | null,
      forecast7_units: null as number | null,
      forecast14_units: null as number | null,
      isForecast: false,
    }));

    const latestHistorical = rows[rows.length - 1];

    // Use the latest observed value as the visual anchor for the dashed
    // forecast segment. It is NOT a model prediction.
    latestHistorical.forecast_units =
      latestHistorical.historical_units;

    if (forecast7.data) {
      rows.push({
        date: forecast7.data.target_date,
        label: formatDateLabel(forecast7.data.target_date),
        historical_units: null,
        forecast_units: forecast7.data.forecast_total_units,
        forecast7_units: forecast7.data.forecast_total_units,
        forecast14_units: null,
        isForecast: true,
      });
    }

    if (forecast14.data) {
      rows.push({
        date: forecast14.data.target_date,
        label: formatDateLabel(forecast14.data.target_date),
        historical_units: null,
        forecast_units: forecast14.data.forecast_total_units,
        forecast7_units: null,
        forecast14_units: forecast14.data.forecast_total_units,
        isForecast: true,
      });
    }

    return rows;
  }, [history.data, forecast7.data, forecast14.data]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Demand Forecast"
        subtitle="XGBoost demand forecast for 7-day and 14-day horizons, shown against recent historical demand."
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
              strictly on the <strong>synthetic sample dataset (2022–2024)</strong>.
              The model improves on the naive 7-day moving-average baseline by
              only approximately 5%, with high sMAPE, so the forecast should be
              treated as decision support rather than a guarantee.
            </p>

            <p className="text-xs text-amber-700">
              <strong>Data Isolation:</strong> Genuine sales entered manually
              (Real · Manual) or imported via CSV (Real · CSV Import) are stored
              separately and are not mixed into this synthetic forecasting
              pipeline.
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

          <label className="flex cursor-pointer items-center gap-2 self-center rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-600 shadow-sm">
            <input
              type="checkbox"
              checked={compareOn}
              onChange={(e) => setCompareOn(e.target.checked)}
              className="accent-brand-600"
            />
            Compare two products
          </label>

          {compareOn && (
            <label className="flex flex-col text-sm font-medium text-gray-700">
              Compare with

              <select
                className="mt-1 rounded-lg border border-gray-300 bg-white px-3 py-1.5 shadow-sm focus:border-brand-500 focus:outline-none"
                value={compareId}
                onChange={(e) => setCompareId(e.target.value)}
              >
                <option value="">Select a product...</option>

                {products.data?.products
                  .filter((product) => product.product_id !== productId)
                  .map((product) => (
                    <option
                      key={product.product_id}
                      value={product.product_id}
                    >
                      {product.product_id} — {product.name} ({product.sku})
                    </option>
                  ))}
              </select>
            </label>
          )}
        </div>
      </Card>

      {!productId && (
        <EmptyState
          title="Select a product to see its demand forecast."
          hint="Forecasts come from the trained XGBoost models for the 7-day and 14-day horizons."
        />
      )}

      {productId && forecastLoading && (
        <LoadingState label="Forecasting..." />
      )}

      {productId && forecastError && !forecastLoading && (
        <ErrorState message={forecastError} />
      )}

      {selectedForecast && !forecastLoading && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Forecast demand at target date"
              value={`${selectedForecast.forecast_total_units.toFixed(0)} units`}
              hint={`Target date: ${selectedForecast.target_date}`}
              accent="info"
            />

            <StatCard
              label="Data source"
              value="Synthetic 2022-2024"
              hint="Real sales are excluded from this model"
              accent="warning"
            />

            <StatCard
              label="Model test MAE"
              value={selectedForecast.model_test_mae.toFixed(1)}
              hint={`Improvement over baseline: ~${
                selectedForecast.baseline_improvement_pct ?? 5
              }%`}
            />

            <StatCard
              label="Selected horizon"
              value={`${selectedForecast.model_horizon_days} days`}
              hint={
                selectedForecast.model_horizon_days !==
                selectedForecast.requested_horizon_days
                  ? `Nearest trained model (requested ${selectedForecast.requested_horizon_days} days)`
                  : "Matches your request"
              }
              accent={
                selectedForecast.model_horizon_days !==
                selectedForecast.requested_horizon_days
                  ? "warning"
                  : "default"
              }
            />
          </div>

          <Card
            title="Historical Demand & Forecast"
            subtitle={`Recent daily demand for ${selectedForecast.product_id} with the model's 7-day and 14-day forecast points`}
          >
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={360}>
                <LineChart
                  data={chartData}
                  margin={{
                    top: 10,
                    right: 20,
                    left: 10,
                    bottom: 10,
                  }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="#e5e7eb"
                  />

                  <XAxis
                    dataKey="label"
                    fontSize={12}
                    tickLine={false}
                    axisLine={{ stroke: "#e5e7eb" }}
                    interval="preserveStartEnd"
                  />

                  <YAxis
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(value: number) =>
                      value.toLocaleString()
                    }
                  />

                  <Tooltip
                    labelFormatter={(_label, payload) => {
                      const item = payload?.[0]?.payload as
                        | {
                            date?: string;
                            isForecast?: boolean;
                          }
                        | undefined;

                      if (!item?.date) {
                        return "";
                      }

                      return `${item.isForecast ? "Forecast date" : "Date"}: ${item.date}`;
                    }}
                    formatter={(value, name) => {
                      if (value === null || value === undefined) {
                        return ["—", String(name)];
                      }

                      return [
                        `${Number(value).toLocaleString()} units`,
                        String(name),
                      ];
                    }}
                  />

                  <Legend />

                  <Line
                    type="monotone"
                    dataKey="historical_units"
                    name="Historical demand"
                    stroke="#2563eb"
                    strokeWidth={3}
                    dot={false}
                    activeDot={{ r: 5 }}
                    connectNulls={false}
                    isAnimationActive={false}
                  />

                  <Line
                    type="linear"
                    dataKey="forecast_units"
                    name="XGBoost forecast"
                    stroke="#f59e0b"
                    strokeWidth={3}
                    strokeDasharray="8 6"
                    dot={{ r: 6 }}
                    activeDot={{ r: 8 }}
                    connectNulls={true}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState
                title="No historical demand is available for this product."
                hint="The chart needs the synthetic sales history used by the forecasting models."
              />
            )}

            <div className="mt-3 rounded-lg bg-gray-50 px-4 py-3 text-xs leading-relaxed text-gray-600">
              <strong>How to read this chart:</strong> the solid line is the
              recent historical daily demand. The dashed line shows the model's
              direct 7-day and 14-day forecast outputs. The last historical value
              is used only as a visual anchor for the forecast segment; the model
              does not generate individual predictions for days 1–6 or 8–13.
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {forecast7.data && (
              <StatCard
                label="7-day forecast"
                value={`${forecast7.data.forecast_total_units.toFixed(0)} units`}
                hint={`Target date: ${forecast7.data.target_date}`}
                accent={horizon === 7 ? "info" : "default"}
              />
            )}

            {forecast14.data && (
              <StatCard
                label="14-day forecast"
                value={`${forecast14.data.forecast_total_units.toFixed(0)} units`}
                hint={`Target date: ${forecast14.data.target_date}`}
                accent={horizon === 14 ? "info" : "default"}
              />
            )}
          </div>

          {compareOn && selectedForecast && (
            <Card
              title="Side-by-side comparison"
              subtitle={
                compareForecast.data
                  ? `${selectedForecast.product_id} (${selectedForecast.forecast_total_units.toFixed(0)} units) vs ${compareForecast.data.product_id} (${compareForecast.data.forecast_total_units.toFixed(0)} units)`
                  : "Pick a second product above to compare per-store demand."
              }
            >
              {compareForecast.loading && <LoadingState label="Forecasting comparison..." />}
              {compareForecast.error && <ErrorState message={compareForecast.error} />}
              {!compareId || compareId === productId ? (
                <EmptyState
                  title="Select a different second product."
                  hint="Comparison needs two distinct products at the same horizon."
                />
              ) : compareForecast.data ? (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={compareRows}>
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
                      dataKey={selectedForecast.product_id}
                      fill="#2563eb"
                      radius={[6, 6, 0, 0]}
                    />
                    <Bar
                      dataKey={compareForecast.data.product_id}
                      fill="#16a34a"
                      radius={[6, 6, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              ) : null}
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
