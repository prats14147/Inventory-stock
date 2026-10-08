// frontend/src/pages/Dashboard.tsx

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
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
  const summaryQuery = useApi(
    () => getDashboardSummary(),
    []
  );

  const summary = summaryQuery.data;

  const {
    loading: summaryLoading,
    error: summaryError,
  } = summaryQuery;

  const highRiskCount =
    summary?.risk_counts?.high ?? 0;

  const mediumRiskCount =
    summary?.risk_counts?.medium ?? 0;

  const lowRiskCount =
    summary?.risk_counts?.low ?? 0;

  /*
   * Only give the donut actual slices for values greater than zero.
   *
   * Previously Recharts tried to position labels for the 0-value
   * Medium and Low slices. Because those slices have no visible
   * area, their labels ended up on top of each other.
   */
  const riskDonutData = [
    {
      name: "High",
      value: highRiskCount,
      color: RISK_COLORS.HIGH,
    },
    {
      name: "Medium",
      value: mediumRiskCount,
      color: RISK_COLORS.MEDIUM,
    },
    {
      name: "Low",
      value: lowRiskCount,
      color: RISK_COLORS.LOW,
    },
  ].filter((item) => item.value > 0);

  const totalRiskCount =
    highRiskCount + mediumRiskCount;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        subtitle={
          summary
            ? `Inventory intelligence across ${summary.product_count} products and ${summary.store_count} stores${
                summary.as_of_date
                  ? `, as of ${summary.as_of_date}`
                  : ""
              }.`
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
              summary in{" "}
              {summary.compute_ms} ms
              {summary.served_from_cache
                ? " · cached"
                : ""}
            </span>
          ) : null
        }
      />

      <NeedsAttentionPanel
        items={
          summary?.needs_attention ??
          []
        }
        loading={
          summaryLoading
        }
        error={
          summaryError
        }
        asOfDate={
          summary?.as_of_date ??
          null
        }
      />

      {/* ------------------------------------------------------------------ */}
      {/* Summary statistics                                                  */}
      {/* ------------------------------------------------------------------ */}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Products"
          value={
            summary?.product_count ??
            0
          }
          hint={`Across ${
            summary?.store_count ??
            0
          } stores`}
        />

        <StatCard
          label="Units on Hand"
          value={(
            summary?.total_inventory_units ??
            0
          ).toLocaleString()}
          hint="Latest inventory date"
        />

        <StatCard
          label="Low Stock Items"
          value={
            summary?.low_stock_count ??
            0
          }
          hint={`Under ${
            summary?.low_stock_threshold ??
            50
          } units`}
          accent={
            summary &&
            summary.low_stock_count > 0
              ? "warning"
              : "success"
          }
        />

        <StatCard
          label="At Stockout Risk"
          value={
            highRiskCount
          }
          hint={
            highRiskCount > 0
              ? mediumRiskCount > 0
                ? `${highRiskCount} high · ${mediumRiskCount} medium`
                : `${highRiskCount} high-risk product${
                    highRiskCount === 1
                      ? ""
                      : "s"
                  }`
              : mediumRiskCount > 0
                ? `${mediumRiskCount} medium-risk product${
                    mediumRiskCount === 1
                      ? ""
                      : "s"
                  }`
                : "No products currently at high risk"
          }
          accent={
            highRiskCount > 0
              ? "danger"
              : mediumRiskCount > 0
                ? "warning"
                : "success"
          }
        />
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Risk + low-stock                                                    */}
      {/* ------------------------------------------------------------------ */}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card
          title="Risk Tier Distribution"
          subtitle="Products by stockout risk level"
        >
          <ResponsiveContainer
            width="100%"
            height={260}
          >
            <PieChart>
              <Pie
                data={riskDonutData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={96}
                paddingAngle={
                  riskDonutData.length > 1
                    ? 3
                    : 0
                }
                dataKey="value"
                nameKey="name"
                labelLine={false}
                label={({ name, percent }) => {
                  const percentage =
                    Number(percent ?? 0) *
                    100;

                  return percentage > 0
                    ? `${name} ${percentage.toFixed(
                        0
                      )}%`
                    : "";
                }}
              >
                {riskDonutData.map(
                  (
                    entry,
                    index
                  ) => (
                    <Cell
                      key={`risk-cell-${index}`}
                      fill={
                        entry.color
                      }
                    />
                  )
                )}
              </Pie>

              <Tooltip
                formatter={(
                  value,
                  name
                ) => [
                  `${Number(
                    value
                  ).toLocaleString()} products`,
                  String(name),
                ]}
              />
            </PieChart>
          </ResponsiveContainer>

          {/* Clean legend outside the donut. This also shows zero values
              without trying to place them on the chart itself. */}
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
            <div className="flex items-center justify-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{
                  backgroundColor:
                    RISK_COLORS.HIGH,
                }}
              />

              <span className="text-sm text-gray-700">
                High{" "}
                <span className="font-semibold tabular-nums text-gray-900">
                  {highRiskCount}
                </span>
                {" "}(
                {highRiskCount +
                  mediumRiskCount +
                  lowRiskCount >
                0
                  ? (
                      (highRiskCount /
                        (highRiskCount +
                          mediumRiskCount +
                          lowRiskCount)) *
                      100
                    ).toFixed(0)
                  : "0"}
                %)
              </span>
            </div>

            <div className="flex items-center justify-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{
                  backgroundColor:
                    RISK_COLORS.MEDIUM,
                }}
              />

              <span className="text-sm text-gray-700">
                Medium{" "}
                <span className="font-semibold tabular-nums text-gray-900">
                  {mediumRiskCount}
                </span>
                {" "}(
                {highRiskCount +
                  mediumRiskCount +
                  lowRiskCount >
                0
                  ? (
                      (mediumRiskCount /
                        (highRiskCount +
                          mediumRiskCount +
                          lowRiskCount)) *
                      100
                    ).toFixed(0)
                  : "0"}
                %)
              </span>
            </div>

            <div className="flex items-center justify-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{
                  backgroundColor:
                    RISK_COLORS.LOW,
                }}
              />

              <span className="text-sm text-gray-700">
                Low{" "}
                <span className="font-semibold tabular-nums text-gray-900">
                  {lowRiskCount}
                </span>
                {" "}(
                {highRiskCount +
                  mediumRiskCount +
                  lowRiskCount >
                0
                  ? (
                      (lowRiskCount /
                        (highRiskCount +
                          mediumRiskCount +
                          lowRiskCount)) *
                      100
                    ).toFixed(0)
                  : "0"}
                %)
              </span>
            </div>
          </div>

          <div className="mt-3 rounded-lg border border-gray-200 bg-white px-3 py-2">
            <p className="text-xs leading-5 text-gray-500">
              Stockout risk looks at expected future
              demand and inventory coverage. A product
              can be high risk even when its current stock
              is above the low-stock threshold.
            </p>
          </div>
        </Card>

        <Card
          title="Low Stock Preview"
          subtitle={`Top ${
            summary?.low_stock_preview
              ?.length ??
            0
          } items below threshold`}
        >
          {summary?.low_stock_preview &&
          summary.low_stock_preview
            .length > 0 ? (
            <ul className="divide-y divide-gray-100">
              {summary.low_stock_preview.map(
                (item) => (
                  <li
                    key={`${item.product_id}-${item.store_id}`}
                    className="flex flex-wrap items-center justify-between gap-3 py-2.5"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link
                          to={`/stockout?product=${encodeURIComponent(
                            item.product_id
                          )}`}
                          className="font-semibold text-gray-900 hover:underline"
                        >
                          {
                            item.name
                          }
                        </Link>

                        <span className="text-xs text-gray-500">
                          (
                          {
                            item.product_id
                          }
                          )
                        </span>

                        <span className="text-xs text-gray-500">
                          ·{" "}
                          {
                            item.sku
                          }
                        </span>

                        <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800 ring-1 ring-inset ring-amber-600/20">
                          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                          Low
                        </span>
                      </div>

                      <p className="mt-0.5 text-xs text-gray-500">
                        Store{" "}
                        {
                          item.store_id
                        }{" "}
                        ·{" "}
                        {
                          item.inventory_level
                        }{" "}
                        units on hand
                        {" "}
                        (threshold:{" "}
                        {
                          item.threshold
                        })
                      </p>
                    </div>

                    <Link
                      to={`/inventory?product=${encodeURIComponent(
                        item.product_id
                      )}`}
                      className="text-xs font-medium text-brand-700 hover:underline"
                    >
                      View
                    </Link>
                  </li>
                )
              )}
            </ul>
          ) : (
            <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-5 text-center">
              <p className="text-sm font-medium text-gray-700">
                No low-stock items.
              </p>

              <p className="mt-1 text-xs leading-5 text-gray-500">
                No inventory rows are currently below
                the configured low-stock threshold of{" "}
                {summary?.low_stock_threshold ??
                  50}{" "}
                units. Products can still appear in
                stockout risk because risk also considers
                forecast demand and inventory coverage.
              </p>

              {totalRiskCount > 0 && (
                <Link
                  to="/stockout"
                  className="mt-3 inline-block text-xs font-medium text-brand-700 hover:underline"
                >
                  Review stockout risk →
                </Link>
              )}
            </div>
          )}
        </Card>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Sales trend + stock movements                                      */}
      {/* ------------------------------------------------------------------ */}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card
          title="7-Day Sales Trend"
          subtitle="Total units sold per day"
        >
          <ResponsiveContainer
            width="100%"
            height={260}
          >
            <LineChart
              data={
                summary?.sales_sparkline ??
                []
              }
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#e5e7eb"
              />

              <XAxis
                dataKey="date"
                fontSize={11}
                tickLine={false}
                axisLine={{
                  stroke:
                    "#e5e7eb",
                }}
                tickFormatter={(
                  value
                ) =>
                  new Date(
                    value
                  ).toLocaleDateString(
                    undefined,
                    {
                      weekday:
                        "short",
                      day: "numeric",
                    }
                  )
                }
              />

              <YAxis
                fontSize={12}
                tickLine={false}
                axisLine={false}
                tickFormatter={(
                  value
                ) =>
                  Number(
                    value
                  ).toLocaleString()
                }
              />

              <Tooltip
                formatter={(
                  value
                ) => [
                  `${Number(
                    value
                  ).toLocaleString()} units`,
                  "Sold",
                ]}
                cursor={{
                  fill: "#eff6ff",
                }}
              />

              <Line
                type="monotone"
                dataKey="units_sold"
                stroke="#2563eb"
                dot={false}
                strokeWidth={2.5}
                activeDot={{
                  r: 6,
                }}
              />
            </LineChart>
          </ResponsiveContainer>
        </Card>

        <Card
          title="Recent Stock Movements"
          subtitle="Last 10 inventory adjustments"
        >
          {summary?.stock_movements_feed &&
          summary.stock_movements_feed
            .length > 0 ? (
            <ul className="divide-y divide-gray-100">
              {summary.stock_movements_feed.map(
                (
                  movement,
                  index
                ) => (
                  <li
                    key={`${movement.occurred_at}-${movement.product_id}-${movement.store_id}-${index}`}
                    className="flex flex-wrap items-center justify-between gap-3 py-2.5"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link
                          to={`/stockout?product=${encodeURIComponent(
                            movement.product_id
                          )}`}
                          className="font-semibold text-gray-900 hover:underline"
                        >
                          {
                            movement.name
                          }
                        </Link>

                        <span className="text-xs text-gray-500">
                          (
                          {
                            movement.product_id
                          }
                          )
                        </span>

                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
                            movement.movement_type ===
                            "DELIVERY"
                              ? "bg-blue-100 text-blue-800"
                              : movement.movement_type ===
                                  "RETURN"
                                ? "bg-green-100 text-green-800"
                                : "bg-amber-100 text-amber-800"
                          }`}
                        >
                          {
                            movement.movement_type
                          }
                        </span>
                      </div>

                      <p className="mt-0.5 text-xs text-gray-500">
                        Store{" "}
                        {
                          movement.store_id
                        }{" "}
                        ·{" "}
                        {movement.quantity_delta >
                        0
                          ? "+"
                          : ""}
                        {
                          movement.quantity_delta
                        }{" "}
                        units (
                        {
                          movement.quantity_before
                        }{" "}
                        →{" "}
                        {
                          movement.quantity_after
                        }
                        ) ·{" "}
                        {
                          movement.reason
                        }
                      </p>
                    </div>

                    <span className="text-xs text-gray-400">
                      {new Date(
                        movement.occurred_at
                      ).toLocaleString()}
                    </span>
                  </li>
                )
              )}
            </ul>
          ) : (
            <p className="text-sm text-gray-500">
              No recent movements.
            </p>
          )}
        </Card>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Best sellers + category sales                                      */}
      {/* ------------------------------------------------------------------ */}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card
          title="Top 5 Products by Units Sold"
          subtitle="All-time best sellers"
          actions={
            <Link
              to="/sales"
              className="text-xs font-medium text-brand-700 hover:underline"
            >
              View all sales →
            </Link>
          }
        >
          <ResponsiveContainer
            width="100%"
            height={260}
          >
            <BarChart
              data={
                summary?.top_products ??
                []
              }
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#e5e7eb"
              />

              <XAxis
                dataKey="product_id"
                fontSize={12}
                tickLine={false}
                axisLine={{
                  stroke:
                    "#e5e7eb",
                }}
              />

              <YAxis
                fontSize={12}
                tickLine={false}
                axisLine={false}
                tickFormatter={(
                  value
                ) =>
                  Number(
                    value
                  ).toLocaleString()
                }
              />

              <Tooltip
                formatter={(
                  value
                ) => [
                  `${Number(
                    value
                  ).toLocaleString()} units`,
                  "Sold",
                ]}
                cursor={{
                  fill: "#eff6ff",
                }}
              />

              <Bar
                dataKey="total_units_sold"
                fill="#2563eb"
                radius={[
                  6,
                  6,
                  0,
                  0,
                ]}
              />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card
          title="Sales by Category"
          subtitle="Units sold per category"
          actions={
            <Link
              to="/sales"
              className="text-xs font-medium text-brand-700 hover:underline"
            >
              Break it down →
            </Link>
          }
        >
          <ResponsiveContainer
            width="100%"
            height={260}
          >
            <BarChart
              data={
                summary?.category_sales ??
                []
              }
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#e5e7eb"
              />

              <XAxis
                dataKey="category"
                fontSize={12}
                tickLine={false}
                axisLine={{
                  stroke:
                    "#e5e7eb",
                }}
              />

              <YAxis
                fontSize={12}
                tickLine={false}
                axisLine={false}
                tickFormatter={(
                  value
                ) =>
                  Number(
                    value
                  ).toLocaleString()
                }
              />

              <Tooltip
                formatter={(
                  value
                ) => [
                  `${Number(
                    value
                  ).toLocaleString()} units`,
                  "Sold",
                ]}
                cursor={{
                  fill: "#f0fdf4",
                }}
              />

              <Bar
                dataKey="total_units_sold"
                fill="#16a34a"
                radius={[
                  6,
                  6,
                  0,
                  0,
                ]}
              />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>
    </div>
  );
}