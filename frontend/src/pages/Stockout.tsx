// frontend/src/pages/Stockout.tsx

import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { exportStockoutCsv, getProducts, getStockoutRiskList } from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";
import RiskBadge from "../components/RiskBadge";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import PinButton from "../components/PinButton";

const STORES = ["S001", "S002", "S003", "S004", "S005"];

export default function Stockout() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlProduct = searchParams.get("product") ?? "";
  const [onlyAtRisk, setOnlyAtRisk] = useState(false);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [storeId, setStoreId] = useState("");

  const productsQuery = useApi(() => getProducts(), []);
  const categories = (productsQuery.data?.products ?? []).map((p) => p.category).filter((c, i, arr) => arr.indexOf(c) === i).sort();

  // Server-side filtering + pagination: the API slices, so this page stays
  // fast as the catalog grows. The deep link (?product=P0001) is applied
  // client-side on top, so watchlist/chat links still land on the exact card.
  const { data, loading, error } = useApi(
    () =>
      getStockoutRiskList({
        onlyAtRisk,
        search: search.trim() || undefined,
        category: category || undefined,
        store_id: storeId || undefined,
        limit: 200,
      }),
    [onlyAtRisk, search, category, storeId]
  );
  const highCount = (data ?? []).filter((item) => item.risk === "HIGH").length;
  const mediumCount = (data ?? []).filter((item) => item.risk === "MEDIUM").length;

  const visible = urlProduct ? (data ?? []).filter((item) => item.product_id === urlProduct) : (data ?? []);

  function clearProduct() {
    const params = new URLSearchParams(searchParams);
    params.delete("product");
    setSearchParams(params, { replace: true });
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Stockout Risk"
        subtitle={
          data
            ? `${highCount} high risk · ${mediumCount} medium risk across ${data.length} products${storeId ? ` · store scope ${storeId}` : ""}.`
            : "Forecast demand vs on-hand inventory over the lead time, with safety stock."
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-600 shadow-sm">
              <input type="checkbox" checked={onlyAtRisk} onChange={(e) => setOnlyAtRisk(e.target.checked)} className="accent-brand-600" />
              Only show at-risk products
            </label>
            <button
              type="button"
              onClick={() => visible.length > 0 && exportStockoutCsv(visible)}
              disabled={visible.length === 0}
              className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Export CSV
            </button>
          </div>
        }
      />

      <div className="flex flex-wrap gap-2">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search product, name, or SKU..."
          className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none sm:w-64"
          aria-label="Search stockout risk"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none"
          aria-label="Filter by category"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          value={storeId}
          onChange={(e) => setStoreId(e.target.value)}
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none"
          aria-label="Store-level risk scope"
          title="Store-level risk apportions product demand evenly across stores"
        >
          <option value="">All stores (product total)</option>
          {STORES.map((s) => (
            <option key={s} value={s}>{s} only</option>
          ))}
        </select>
        {(search || category || storeId) && (
          <button
            type="button"
            onClick={() => { setSearch(""); setCategory(""); setStoreId(""); }}
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-50"
          >
            Clear filters
          </button>
        )}
      </div>

      {urlProduct && !loading && !error && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-brand-800">
          <span>
            Showing <span className="font-semibold">{urlProduct}</span> only.
          </span>
          <button
            type="button"
            onClick={clearProduct}
            className="rounded-lg border border-brand-300 bg-white px-2 py-0.5 text-xs font-medium text-brand-700 hover:bg-brand-100"
          >
            Show all products
          </button>
        </div>
      )}

      {loading && <LoadingState label="Calculating stockout risk..." />}
      {error && <ErrorState message={error} />}

      {!loading && !error && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {visible.map((item) => (
              <Card
                key={`${item.product_id}-${item.store_id ?? "all"}`}
                className={
                  item.risk === "HIGH"
                    ? "border-l-4 border-l-red-500"
                    : item.risk === "MEDIUM"
                      ? "border-l-4 border-l-amber-500"
                      : "border-l-4 border-l-green-500"
                }
              >
                <div className="mb-2 flex items-center justify-between">
                  <div>
                    <span className="font-semibold text-gray-900">{item.name}</span>
                    <span className="ml-2 text-sm text-gray-500">({item.product_id})</span>
                    <div className="text-xs text-gray-400">{item.sku} · {item.category}{item.store_id ? ` · ${item.store_id}` : ""}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <RiskBadge risk={item.risk} />
                    <PinButton productId={item.product_id} />
                  </div>
                </div>
                <dl className="space-y-1 text-sm text-gray-600">
                  <div className="flex justify-between">
                    <dt>Current inventory</dt>
                    <dd className="tabular-nums font-medium text-gray-900">{item.current_inventory.toFixed(0)}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Forecast demand ({item.lead_time_days}d lead time)</dt>
                    <dd className="tabular-nums">{item.forecast_lead_time_demand.toFixed(1)}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Safety stock</dt>
                    <dd className="tabular-nums">{item.safety_stock.toFixed(1)}</dd>
                  </div>
                  <div className="flex justify-between border-t border-gray-100 pt-1 font-medium text-gray-800">
                    <dt>Required inventory</dt>
                    <dd className="tabular-nums">{item.required_inventory.toFixed(1)}</dd>
                  </div>
                </dl>
                <p className="mt-3 border-t border-gray-100 pt-2 text-xs text-gray-500">{item.reason}</p>
                <div className="mt-2 flex gap-3 text-xs font-medium">
                  <a href={`/reorder`} className="text-brand-700 hover:underline">
                    Reorder →
                  </a>
                  <a href={`/forecast?product=${item.product_id}`} className="text-brand-700 hover:underline">
                    Forecast →
                  </a>
                </div>
              </Card>
            ))}
          </div>
          {visible.length === 0 && (
            <EmptyState
              title={
                urlProduct
                  ? `No risk record for ${urlProduct}.`
                  : onlyAtRisk
                    ? "No at-risk products right now."
                    : "No products match this filter."
              }
              hint={
                urlProduct
                  ? "Clear the product filter to see every product."
                  : "Widen the search, category, or store filters — or check the Reorder page for order quantities."
              }
            />
          )}
        </>
      )}
    </div>
  );
}
