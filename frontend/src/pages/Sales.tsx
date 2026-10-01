// frontend/src/pages/Sales.tsx

import { useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, BarChart, Bar } from "recharts";
import { useApi } from "../hooks/useApi";
import { getTopProducts, getSalesByCategory, getSalesByStore, getSalesTrend } from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";

export default function Sales() {
  const [granularity, setGranularity] = useState<"daily" | "weekly" | "monthly">("monthly");

  const top = useApi(() => getTopProducts(10), []);
  const byCategory = useApi(() => getSalesByCategory(), []);
  const byStore = useApi(() => getSalesByStore(), []);
  const trend = useApi(() => getSalesTrend({ granularity }), [granularity]);

  const anyLoading = [top, byCategory, byStore, trend].some((q) => q.loading);
  const firstError = [top, byCategory, byStore, trend].find((q) => q.error)?.error;

  if (anyLoading) return <LoadingState label="Loading sales data..." />;
  if (firstError) return <ErrorState message={firstError} />;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Sales Analytics</h1>

      <div className="rounded-lg border bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-gray-600">Sales Trend</h2>
          <select
            className="rounded-md border px-2 py-1 text-sm"
            value={granularity}
            onChange={(e) => setGranularity(e.target.value as "daily" | "weekly" | "monthly")}
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </div>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={trend.data?.points ?? []}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" fontSize={11} />
            <YAxis fontSize={12} />
            <Tooltip />
            <Line type="monotone" dataKey="total_units_sold" stroke="#2563eb" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-medium text-gray-600">Top-Selling Products</h2>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={top.data?.products ?? []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" fontSize={11} />
              <YAxis type="category" dataKey="product_id" fontSize={11} width={50} />
              <Tooltip />
              <Bar dataKey="total_units_sold" fill="#2563eb" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-medium text-gray-600">Sales by Category</h2>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={byCategory.data ?? []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="category" fontSize={10} />
              <YAxis fontSize={11} />
              <Tooltip />
              <Bar dataKey="total_units_sold" fill="#55a868" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-medium text-gray-600">Sales by Store</h2>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={byStore.data ?? []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="store_id" fontSize={11} />
              <YAxis fontSize={11} />
              <Tooltip />
              <Bar dataKey="total_units_sold" fill="#c44e52" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
