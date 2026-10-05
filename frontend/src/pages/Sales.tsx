// frontend/src/pages/Sales.tsx

import { FormEvent, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, BarChart, Bar } from "recharts";
import { ApiError, getCurrentInventory, getProductCosts, getStoreProfitability, getTopProducts, getSalesByCategory, getSalesByStore, getSalesTrend, recordSale } from "../services/api";
import { useApi } from "../hooks/useApi";
import { LoadingState, ErrorState } from "../components/LoadingError";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";

export default function Sales() {
  const [granularity, setGranularity] = useState<"daily" | "weekly" | "monthly">("monthly");
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedStockKey, setSelectedStockKey] = useState("");
  const [unitsSold, setUnitsSold] = useState("1");
  const [unitPrice, setUnitPrice] = useState("");
  const [unitCost, setUnitCost] = useState("");
  const [saleCategory, setSaleCategory] = useState("Groceries");
  const [saleRegion, setSaleRegion] = useState("East");
  const [savingSale, setSavingSale] = useState(false);
  const [saleError, setSaleError] = useState("");
  const [saleSuccess, setSaleSuccess] = useState("");

  const stock = useApi(() => getCurrentInventory(), [refreshKey]);
  const top = useApi(() => getTopProducts(10), [refreshKey]);
  const byCategory = useApi(() => getSalesByCategory(), [refreshKey]);
  const byStore = useApi(() => getSalesByStore(), [refreshKey]);
  const trend = useApi(() => getSalesTrend({ granularity }), [granularity, refreshKey]);
  const productCosts = useApi(() => getProductCosts(), [refreshKey]);
  const profitability = useApi(() => getStoreProfitability(), [refreshKey]);

  const stockRows = stock.data ?? [];
  const selectedStock = useMemo(
    () => stockRows.find((row) => `${row.product_id}::${row.store_id}` === selectedStockKey),
    [stockRows, selectedStockKey]
  );

  function selectStock(key: string) {
    setSelectedStockKey(key);
    const row = stockRows.find((item) => `${item.product_id}::${item.store_id}` === key);
    if (row) {
      setSaleCategory(row.category === "Uncategorized" ? "Groceries" : row.category);
      setSaleRegion(row.region === "Unassigned" ? "East" : row.region);
      const knownCost = productCosts.data?.products.find((product) => product.product_id === row.product_id)?.cost_price;
      setUnitCost(knownCost == null ? "" : String(knownCost));
    }
  }

  async function submitSale(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedStock) return;
    setSavingSale(true);
    setSaleError("");
    setSaleSuccess("");
    try {
      const result = await recordSale({
        product_id: selectedStock.product_id,
        store_id: selectedStock.store_id,
        units_sold: Number(unitsSold),
        price: Number(unitPrice),
        unit_cost: Number(unitCost),
        category: saleCategory,
        region: saleRegion,
      });
      setSaleSuccess(`Sale recorded. ${result.remaining_inventory} units remain for ${result.product_id} at ${result.store_id}. ${result.gross_profit == null ? "No cost price was saved, so this sale is excluded from profit reporting." : `Estimated gross profit/loss: ${result.gross_profit.toFixed(2)}.`}`);
      setRefreshKey((key) => key + 1);
    } catch (err) {
      setSaleError(err instanceof ApiError ? err.message : "Could not record the sale. Please try again.");
    } finally {
      setSavingSale(false);
    }
  }

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

      <Card title="Record a sale" subtitle="Each sale is added to sales history and deducted from stock on hand.">
        <form onSubmit={submitSale} className="space-y-4">
          {stock.error && <p role="alert" className="text-sm text-red-700">{stock.error}</p>}
          {stockRows.length === 0 && !stock.loading && !stock.error && <p className="text-sm text-gray-600">Add product stock on the Inventory page before recording a sale.</p>}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <label className="space-y-1 text-sm font-medium text-gray-700">Product at store
              <select required value={selectedStockKey} onChange={(event) => selectStock(event.target.value)} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-normal">
                <option value="" disabled>{stock.loading ? "Loading stock…" : "Select product and store"}</option>
                {stockRows.map((row) => <option key={`${row.product_id}::${row.store_id}`} value={`${row.product_id}::${row.store_id}`}>{row.product_id} · {row.store_id} · {row.inventory_level} on hand</option>)}
              </select>
            </label>
            <label className="space-y-1 text-sm font-medium text-gray-700">Quantity sold
              <input required type="number" min="1" max={selectedStock?.inventory_level} step="1" value={unitsSold} onChange={(event) => setUnitsSold(event.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal" />
            </label>
            <label className="space-y-1 text-sm font-medium text-gray-700">Unit price
              <input required type="number" min="0" step="0.01" value={unitPrice} onChange={(event) => setUnitPrice(event.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal" />
            </label>
            <label className="space-y-1 text-sm font-medium text-gray-700">Unit cost
              <input required type="number" min="0" step="0.01" value={unitCost} onChange={(event) => setUnitCost(event.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal" />
            </label>
            <label className="space-y-1 text-sm font-medium text-gray-700">Category
              <select required value={saleCategory} onChange={(event) => setSaleCategory(event.target.value)} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-normal">
                {["Furniture", "Toys", "Clothing", "Groceries", "Electronics"].map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className="space-y-1 text-sm font-medium text-gray-700">Region
              <select required value={saleRegion} onChange={(event) => setSaleRegion(event.target.value)} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-normal">
                {["North", "South", "East", "West"].map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
          </div>
          <p className="text-xs text-gray-500">Unit cost is prefilled from the product catalog when available. The sale keeps its own price and cost snapshot for profit reports; changing a product's default later will not rewrite older sales.</p>
          {saleError && <p role="alert" className="text-sm text-red-700">{saleError}</p>}
          {saleSuccess && <p role="status" className="text-sm text-green-700">{saleSuccess}</p>}
          <button disabled={savingSale || stock.loading || !selectedStock} type="submit" className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50">{savingSale ? "Recording…" : "Record sale and update stock"}</button>
        </form>
      </Card>

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

      <Card title="Store Profit and Loss" subtitle="Gross profit on recorded sales that have a saved unit cost. Historical sample sales without costs are excluded.">
        {profitability.loading ? <p className="text-sm text-gray-500">Calculating store results…</p> : profitability.error ? <ErrorState message={profitability.error} /> : (profitability.data?.items.length ?? 0) === 0 ? (
          <p className="text-sm text-gray-600">Record sales with unit cost to see which stores are profitable or operating at a loss.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b text-xs uppercase text-gray-500"><tr><th className="px-3 py-2">Store</th><th className="px-3 py-2">Net revenue (costed)</th><th className="px-3 py-2">Cost of goods</th><th className="px-3 py-2">Gross profit/loss</th><th className="px-3 py-2">Cost coverage</th><th className="px-3 py-2">Condition</th></tr></thead>
              <tbody className="divide-y">
                {profitability.data?.items.map((item) => <tr key={item.store_id}>
                  <td className="px-3 py-2 font-medium">{item.store_id}</td>
                  <td className="px-3 py-2">{item.costed_net_revenue.toFixed(2)}</td>
                  <td className="px-3 py-2">{item.known_cost_of_goods_sold.toFixed(2)}</td>
                  <td className={`px-3 py-2 font-semibold ${item.condition === "loss" ? "text-red-700" : item.condition === "profit" ? "text-green-700" : "text-gray-600"}`}>{item.gross_profit_or_loss == null ? "Unknown" : `${item.gross_profit_or_loss.toFixed(2)}`}</td>
                  <td className="px-3 py-2">{item.cost_coverage_percent.toFixed(0)}%</td>
                  <td className="px-3 py-2 capitalize">{item.condition.replace("_", " ")}</td>
                </tr>)}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-3 text-xs text-gray-500">{profitability.data?.cost_note}</p>
      </Card>
    </div>
  );
}
