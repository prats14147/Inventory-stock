// frontend/src/pages/Dashboard.tsx

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { useApi } from "../hooks/useApi";
import { getDashboardSummary } from "../services/api";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import StatCard from "../components/StatCard";
import NeedsAttentionPanel from "../components/NeedsAttentionPanel";

export default function Dashboard() {
  // Tier A: the whole page comes from ONE request. It used to be five, and the
  // page blocked on all of them before rendering anything.
  const summaryQuery = useApi(() => getDashboardSummary(), []);

  // Tier A: only a hard failure blanks the page. While the summary is in
  // flight each section below renders its own loading state, so the page fills
  // in progressively instead of showing one spinner for everything.
  const summary = summaryQuery.data;
  const { loading: summaryLoading, error: summaryError } = summaryQuery;

  const highRiskCount = summary?.risk_counts.high ?? 0;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        subtitle={
          summary
            ? `Inventory intelligence across ${summary.product_count} products and ${summary.store_count} stores${summary.as_of_date ? `, as of ${summary.as_of_date}` : ""}.`
            : "Today's inventory health at a glance — what needs attention and top sellers."
        }
        actions={
          summary ? (
            <span
              className="rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs text-gray-500"
              title={
                summary.served_from_cache
                  ? "Risk figures were served from the server's in-process cache."
                  : "Risk figures were recomputed for this request."
              }
            >
              summary in {summary.compute_ms} ms{summary.served_from_cache ? " · cached" : ""}
            </span>
          ) : null
        }
      />

      {/* Tier B: the "what do I do first" block, at the very top. */}
      <NeedsAttentionPanel
        items={summary?.needs_attention ?? []}
        loading={summaryLoading}
        error={summaryError}
        asOfDate={summary?.as_of_date ?? null}
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Products"
          value={summary?.product_count ?? 0}
          hint={`Across ${summary?.store_count ?? 0} stores`}
        />
        <StatCard
          label="Units on Hand"
          value={(summary?.total_inventory_units ?? 0).toLocaleString()}
          hint="Latest inventory date"
        />
        <StatCard
          label="Low Stock Items"
          value={summary?.low_stock_count ?? 0}
          hint={`Under ${summary?.low_stock_threshold ?? 50} units`}
          accent={summary && summary.low_stock_count > 0 ? "warning" : "success"}
        />
        <StatCard
          label="At Stockout Risk"
          value={highRiskCount}
          hint={
            summary && summary.risk_counts.medium > 0
              ? `+${summary.risk_counts.medium} medium risk`
              : "All clear"
          }
          accent={highRiskCount > 0 ? "danger" : "success"}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card
          title="Top 5 Products by Units Sold"
          subtitle="All-time best sellers"
          actions={
            <a href="/sales" className="text-xs font-medium text-brand-700 hover:underline">
              View all sales →
            </a>
          }
        >
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={summary?.top_products ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="product_id" fontSize={12} tickLine={false} axisLine={{ stroke: "#e5e7eb" }} />
              <YAxis fontSize={12} tickLine={false} axisLine={false} tickFormatter={(v: number) => v.toLocaleString()} />
              <Tooltip formatter={(v) => [`${Number(v).toLocaleString()} units`, "Sold"]} cursor={{ fill: "#eff6ff" }} />
              <Bar dataKey="total_units_sold" fill="#2563eb" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card
          title="Sales by Category"
          subtitle="Units sold per category"
          actions={
            <a href="/sales" className="text-xs font-medium text-brand-700 hover:underline">
              Break it down →
            </a>
          }
        >
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={summary?.category_sales ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="category" fontSize={12} tickLine={false} axisLine={{ stroke: "#e5e7eb" }} />
              <YAxis fontSize={12} tickLine={false} axisLine={false} tickFormatter={(v: number) => v.toLocaleString()} />
              <Tooltip formatter={(v) => [`${Number(v).toLocaleString()} units`, "Sold"]} cursor={{ fill: "#f0fdf4" }} />
              <Bar dataKey="total_units_sold" fill="#16a34a" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>
    </div>
  );
}
