// frontend/src/pages/Dashboard.tsx

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, LineChart, Line, PieChart, Pie, Cell } from "recharts";
import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { getDashboardSummary } from "../services/api";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import StatCard from "../components/StatCard";
import NeedsAttentionPanel from "../components/NeedsAttentionPanel";

const RISK_COLORS = {
  HIGH: "#dc2626",
  MEDIUM: "#f59e0b",
  LOW: "#16a34a",
};

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
  const mediumRiskCount = summary?.risk_counts.medium ?? 0;
  const lowRiskCount = summary?.risk_counts.low ?? 0;

  const riskDonutData = [
    { name: "High", value: highRiskCount, color: RISK_COLORS.HIGH },
    { name: "Medium", value: mediumRiskCount, color: RISK_COLORS.MEDIUM },
    { name: "Low", value: lowRiskCount, color: RISK_COLORS.LOW },
  ];

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

      {/* Risk Tier Donut Chart + Low Stock Preview */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Risk Tier Distribution" subtitle="Products by stockout risk level">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={riskDonutData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={2}
                dataKey="value"
                nameKey="name"
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                labelLine={false}
              >
                {riskDonutData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip formatter={(value: number, name: string) => [`${value} products`, name]} />
            </PieChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Low Stock Preview" subtitle={`Top ${summary?.low_stock_preview?.length ?? 0} items below threshold`}>
          {summary?.low_stock_preview && summary.low_stock_preview.length > 0 ? (
            <ul className="divide-y divide-gray-100">
              {summary.low_stock_preview.map((item) => (
                <li key={`${item.product_id}-${item.store_id}`} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link to={`/stockout?product=${item.product_id}`} className="font-semibold text-gray-900 hover:underline">
                        {item.name}
                      </Link>
                      <span className="text-xs text-gray-500">({item.product_id})</span>
                      <span className="text-xs text-gray-500">· {item.sku}</span>
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800 ring-1 ring-inset ring-amber-600/20">
                        <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                        Low
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-gray-500">
                      Store {item.store_id} · {item.inventory_level} units on hand (threshold: {item.threshold})
                    </p>
                  </div>
                  <a
                    href={`/inventory?product=${item.product_id}`}
                    className="text-xs font-medium text-brand-700 hover:underline"
                  >
                    View
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-500">No low-stock items.</p>
          )}
        </Card>
      </div>

      {/* 7-Day Sales Sparkline + Recent Stock Movements Feed */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="7-Day Sales Trend" subtitle="Total units sold per day">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={summary?.sales_sparkline ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="date" fontSize={11} tickLine={false} axisLine={{ stroke: "#e5e7eb" }} tickFormatter={(d: string) => new Date(d).toLocaleDateString(undefined, { weekday: "short", day: "numeric" })} />
              <YAxis fontSize={12} tickLine={false} axisLine={false} tickFormatter={(v: number) => v.toLocaleString()} />
              <Tooltip formatter={(v) => [`${Number(v).toLocaleString()} units`, "Sold"]} cursor={{ fill: "#eff6ff" }} />
              <Line
                type="monotone"
                dataKey="units_sold"
                stroke="#2563eb"
                dot={false}
                strokeWidth={2.5}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Recent Stock Movements" subtitle="Last 10 inventory adjustments">
          {summary?.stock_movements_feed && summary.stock_movements_feed.length > 0 ? (
            <ul className="divide-y divide-gray-100">
              {summary.stock_movements_feed.map((m) => (
                <li key={m.occurred_at} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link to={`/stockout?product=${m.product_id}`} className="font-semibold text-gray-900 hover:underline">
                        {m.name}
                      </Link>
                      <span className="text-xs text-gray-500">({m.product_id})</span>
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
                          m.movement_type === "DELIVERY"
                            ? "bg-blue-100 text-blue-800"
                            : m.movement_type === "RETURN"
                              ? "bg-green-100 text-green-800"
                              : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {m.movement_type}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-gray-500">
                      Store {m.store_id} · {m.quantity_delta > 0 ? "+" : ""}{m.quantity_delta} units ({m.quantity_before} → {m.quantity_after}) · {m.reason}
                    </p>
                  </div>
                  <span className="text-xs text-gray-400">{new Date(m.occurred_at).toLocaleString()}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-500">No recent movements.</p>
          )}
        </Card>
      </div>

      {/* Existing charts */}
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
