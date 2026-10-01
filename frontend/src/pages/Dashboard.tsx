// frontend/src/pages/Dashboard.tsx

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { useApi } from "../hooks/useApi";
import { getProducts, getLowStock, getStockoutRiskList, getSalesByCategory, getTopProducts } from "../services/api";
import StatCard from "../components/StatCard";
import { LoadingState, ErrorState } from "../components/LoadingError";

export default function Dashboard() {
  const products = useApi(() => getProducts(), []);
  const lowStock = useApi(() => getLowStock(), []);
  const atRisk = useApi(() => getStockoutRiskList(true), []);
  const categorySales = useApi(() => getSalesByCategory(), []);
  const topProducts = useApi(() => getTopProducts(5), []);

  const anyLoading = [products, lowStock, atRisk, categorySales, topProducts].some((q) => q.loading);
  const firstError = [products, lowStock, atRisk, categorySales, topProducts].find((q) => q.error)?.error;

  if (anyLoading) return <LoadingState label="Loading dashboard..." />;
  if (firstError) return <ErrorState message={firstError} />;

  const highRiskCount = atRisk.data?.filter((r) => r.risk === "HIGH").length ?? 0;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Dashboard</h1>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total Products" value={products.data?.count ?? 0} />
        <StatCard label="Total Units Sold (all time)" value={(topProducts.data?.products.reduce((a, p) => a + p.total_units_sold, 0) ?? 0).toLocaleString()} />
        <StatCard label="Low Stock Items" value={lowStock.data?.count ?? 0} accent={lowStock.data && lowStock.data.count > 0 ? "warning" : "default"} />
        <StatCard label="High Stockout Risk" value={highRiskCount} accent={highRiskCount > 0 ? "danger" : "default"} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-medium text-gray-600">Top 5 Products by Units Sold</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={topProducts.data?.products ?? []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="product_id" fontSize={12} />
              <YAxis fontSize={12} />
              <Tooltip />
              <Bar dataKey="total_units_sold" fill="#2563eb" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-medium text-gray-600">Sales by Category</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={categorySales.data ?? []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="category" fontSize={12} />
              <YAxis fontSize={12} />
              <Tooltip />
              <Bar dataKey="total_units_sold" fill="#55a868" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
