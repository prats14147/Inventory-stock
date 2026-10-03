// frontend/src/pages/Sales.tsx

import { useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, BarChart, Bar } from "recharts";
import { useApi } from "../hooks/useApi";
import { getTopProducts, getSalesByCategory, getSalesByStore, getSalesTrend } from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";

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
      <PageHeader
        title="Sales Analytics"
        subtitle="Trends, best sellers, and breakdowns by category and store — all from real sales records."
      />

      <Card
        title="Sales Trend"
        subtitle={`${granularity} granularity`}
        actions={
          <select
            className="rounded-lg border border-gray-300 bg-white px-2 py-1 text-sm shadow-sm focus:border-brand-500 focus:outline-none"
            value={granularity}
            onChange={(e) => setGranularity(e.target.value as "daily" | "weekly" | "monthly")}
            aria-label="Trend granularity"
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        }
      >
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={trend.data?.points ?? []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="period" fontSize={11} tickLine={false} axisLine={{ stroke: "#e5e7eb" }} />
            <YAxis fontSize={12} tickLine={false} axisLine={false} tickFormatter={(v: number) => v.toLocaleString()} />
            <Tooltip formatter={(v) => [`${Number(v).toLocaleString()} units`, "Sold"]} />
            <Line type="monotone" dataKey="total_units_sold" stroke="#2563eb" dot={false} strokeWidth={2.5} />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Top-Selling Products" subtitle="Top 10 by units sold">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={top.data?.products ?? []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis type="number" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="product_id" fontSize={11} width={50} tickLine={false} axisLine={false} />
              <Tooltip formatter={(v) => [`${Number(v).toLocaleString()} units`, "Sold"]} cursor={{ fill: "#eff6ff" }} />
              <Bar dataKey="total_units_sold" fill="#2563eb" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Sales by Category" subtitle="Units sold per category">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={byCategory.data ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="category" fontSize={10} tickLine={false} axisLine={{ stroke: "#e5e7eb" }} />
              <YAxis fontSize={11} tickLine={false} axisLine={false} tickFormatter={(v: number) => v.toLocaleString()} />
              <Tooltip formatter={(v) => [`${Number(v).toLocaleString()} units`, "Sold"]} cursor={{ fill: "#f0fdf4" }} />
              <Bar dataKey="total_units_sold" fill="#16a34a" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Sales by Store" subtitle="Units sold per store">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={byStore.data ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="store_id" fontSize={11} tickLine={false} axisLine={{ stroke: "#e5e7eb" }} />
              <YAxis fontSize={11} tickLine={false} axisLine={false} tickFormatter={(v: number) => v.toLocaleString()} />
              <Tooltip formatter={(v) => [`${Number(v).toLocaleString()} units`, "Sold"]} cursor={{ fill: "#fef2f2" }} />
              <Bar dataKey="total_units_sold" fill="#dc2626" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>
    </div>
  );
}
