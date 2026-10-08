// frontend/src/pages/Reorder.tsx

import { useState } from "react";
import { useApi } from "../hooks/useApi";
import {
  ApiError,
  cancelPurchaseOrder,
  createPurchaseOrder,
  getProducts,
  getReorderList,
  listPurchaseOrders,
  receivePurchaseOrder,
} from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import StatCard from "../components/StatCard";
import PinButton from "../components/PinButton";
import { downloadCsv, toCsv } from "../lib/csv";

const STORES = ["S001", "S002", "S003", "S004", "S005"];

export default function Reorder() {
  const [onlyNeeded, setOnlyNeeded] = useState(true);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [storeId, setStoreId] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  // Create-PO form state
  const [poProduct, setPoProduct] = useState("");
  const [poStore, setPoStore] = useState("S001");
  const [poQty, setPoQty] = useState("");
  const [poNote, setPoNote] = useState("");
  const [poError, setPoError] = useState("");
  const [poSuccess, setPoSuccess] = useState("");
  const [poBusy, setPoBusy] = useState(false);
  const [poActionId, setPoActionId] = useState<number | null>(null);

  const productsQuery = useApi(() => getProducts(), []);
  const categories = (productsQuery.data?.products ?? []).map((p) => p.category).filter((c, i, arr) => arr.indexOf(c) === i).sort();

  const { data, loading, error } = useApi(
    () =>
      getReorderList({
        onlyNeeded,
        search: search.trim() || undefined,
        category: category || undefined,
        store_id: storeId || undefined,
        limit: 200,
      }),
    [onlyNeeded, search, category, storeId, refreshKey]
  );
  const ordersQuery = useApi(() => listPurchaseOrders(), [refreshKey]);

  const totalQty = (data ?? []).reduce((sum, r) => sum + r.recommended_reorder_quantity, 0);

  // Exports exactly what the table shows, so the file and the screen can never
  // disagree about which filter was applied.
  function exportCsv() {
    if (!data || data.length === 0) return;
    const headers = [
      "Product",
      "Name",
      "SKU",
      "Category",
      "Store",
      "As of date",
      "Current inventory",
      "Forecast lead-time demand",
      "Safety stock",
      "Recommended order qty",
    ];
    const rows = data.map((r) => [
      r.product_id,
      r.name,
      r.sku,
      r.category,
      r.store_id ?? "all",
      r.as_of_date,
      r.current_inventory.toFixed(0),
      r.forecast_lead_time_demand.toFixed(1),
      r.safety_stock.toFixed(1),
      r.recommended_reorder_quantity.toFixed(0),
    ]);
    const scope = onlyNeeded ? "needing-reorder" : "all-products";
    downloadCsv(`reorder-${scope}-${new Date().toISOString().slice(0, 10)}.csv`, toCsv(headers, rows));
  }

  function prefillPo(productId: string, qty: number) {
    setPoProduct(productId);
    setPoQty(String(Math.max(1, Math.round(qty))));
    setPoError("");
    setPoSuccess("");
  }

  async function submitPo() {
    setPoError("");
    setPoSuccess("");
    if (!poProduct || !poStore || !poQty) {
      setPoError("Pick a product, a store, and a quantity.");
      return;
    }
    setPoBusy(true);
    try {
      const order = await createPurchaseOrder({
        product_id: poProduct,
        store_id: poStore,
        quantity: Number(poQty),
        note: poNote.trim(),
      });
      setPoSuccess(`PO #${order.id} created: ${order.quantity} units of ${order.product_id} for ${order.store_id}. Outstanding orders reserved.`);
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setPoError(err instanceof ApiError ? err.message : "Could not create the purchase order.");
    } finally {
      setPoBusy(false);
    }
  }

  async function handleReceive(id: number) {
    setPoActionId(id);
    setPoError("");
    try {
      const res = await receivePurchaseOrder(id);
      setPoSuccess(`PO #${id} received: delivery recorded for ${res.order.product_id} at ${res.order.store_id}.`);
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setPoError(err instanceof ApiError ? err.message : `Could not receive PO #${id}.`);
    } finally {
      setPoActionId(null);
    }
  }

  async function handleCancel(id: number) {
    setPoActionId(id);
    try {
      await cancelPurchaseOrder(id);
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setPoError(err instanceof ApiError ? err.message : `Could not cancel PO #${id}.`);
    } finally {
      setPoActionId(null);
    }
  }

  const draftOrders = (ordersQuery.data?.orders ?? []).filter((o) => o.status === "DRAFT");
  const pastOrders = (ordersQuery.data?.orders ?? []).filter((o) => o.status !== "DRAFT").slice(0, 10);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Reorder Recommendations"
        subtitle={
          data && data.length > 0
            ? `${data.length} product${data.length === 1 ? "" : "s"} need reordering · ${totalQty.toFixed(0)} units total${storeId ? ` · store scope ${storeId}` : ""}.`
            : "Order quantities from forecast demand plus safety stock, minus what's on hand."
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-600 shadow-sm">
              <input type="checkbox" checked={onlyNeeded} onChange={(e) => setOnlyNeeded(e.target.checked)} className="accent-brand-600" />
              Only show products that need reordering
            </label>
            <button
              type="button"
              onClick={exportCsv}
              disabled={!data || data.length === 0}
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
          aria-label="Search reorder recommendations"
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
          aria-label="Store-level reorder scope"
          title="Store-level reorder apportions product demand evenly across stores"
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

      {!loading && !error && (data ?? []).length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard label="Products to reorder" value={data?.length ?? 0} accent="warning" />
          <StatCard label="Total units to order" value={totalQty.toFixed(0)} hint="Sum of recommended quantities" accent="info" />
          <StatCard
            label="Largest single order"
            value={Math.max(...(data ?? []).map((r) => r.recommended_reorder_quantity)).toFixed(0)}
            hint={(data ?? []).sort((a, b) => b.recommended_reorder_quantity - a.recommended_reorder_quantity)[0]?.product_id ?? ""}
          />
        </div>
      )}

      {loading && <LoadingState label="Calculating reorder recommendations..." />}
      {error && <ErrorState message={error} />}

      {!loading && !error && (
        <Card>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  {["Product", "SKU", "Category", "Current Inventory", "Expected Demand", "Safety Stock", "Recommended Order Qty", ""].map(
                    (h) => (
                      <th key={h} className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {(data ?? []).map((r) => (
                  <tr key={`${r.product_id}-${r.store_id ?? "all"}`} className="transition-colors hover:bg-brand-50/50">
                    <td className="whitespace-nowrap px-4 py-2">
                      <div className="font-medium text-gray-900">{r.name}</div>
                      <div className="text-xs text-gray-500">{r.product_id}{r.store_id ? ` · ${r.store_id}` : ""}</div>
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 text-gray-600">{r.sku}</td>
                    <td className="whitespace-nowrap px-4 py-2 text-gray-600">{r.category}</td>
                    <td className="whitespace-nowrap px-4 py-2 tabular-nums text-gray-600">{r.current_inventory.toFixed(0)}</td>
                    <td className="whitespace-nowrap px-4 py-2 tabular-nums text-gray-600">{r.forecast_lead_time_demand.toFixed(1)}</td>
                    <td className="whitespace-nowrap px-4 py-2 tabular-nums text-gray-600">{r.safety_stock.toFixed(1)}</td>
                    <td className="whitespace-nowrap px-4 py-2 tabular-nums font-semibold text-brand-700">
                      {r.recommended_reorder_quantity.toFixed(0)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <PinButton productId={r.product_id} />
                        <button
                          type="button"
                          onClick={() => prefillPo(r.product_id, r.recommended_reorder_quantity)}
                          className="rounded-md border border-brand-300 px-2 py-1 text-xs font-medium text-brand-700 hover:bg-brand-50"
                        >
                          Create PO
                        </button>
                        <a href={`/forecast?product=${r.product_id}`} className="text-xs font-medium text-brand-700 hover:underline">
                          Forecast →
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(data ?? []).length === 0 && (
            <div className="mt-3">
              <EmptyState
                title="Nothing needs reordering."
                hint="Every product covers its forecast demand plus safety stock. Widen the filters to see all products."
              />
            </div>
          )}
        </Card>
      )}

      {/* Purchase order flow */}
      <Card title="Purchase orders" subtitle="Draft a PO from a recommendation; receiving it posts a DELIVERY stock adjustment.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <label className="space-y-1 text-sm font-medium text-gray-700">
            Product
            <select
              value={poProduct}
              onChange={(e) => setPoProduct(e.target.value)}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-normal"
            >
              <option value="">Select…</option>
              {(productsQuery.data?.products ?? []).map((p) => (
                <option key={p.product_id} value={p.product_id}>{p.product_id} — {p.name}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm font-medium text-gray-700">
            Store
            <select
              value={poStore}
              onChange={(e) => setPoStore(e.target.value)}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-normal"
            >
              {STORES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm font-medium text-gray-700">
            Quantity
            <input
              type="number"
              min="1"
              step="1"
              value={poQty}
              onChange={(e) => setPoQty(e.target.value)}
              placeholder="e.g. 120"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal"
            />
          </label>
          <label className="space-y-1 text-sm font-medium text-gray-700 sm:col-span-2">
            Note (optional)
            <input
              type="text"
              value={poNote}
              onChange={(e) => setPoNote(e.target.value)}
              placeholder="e.g. Supplier Acme, ETA Friday"
              maxLength={500}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal"
            />
          </label>
        </div>
        {poError && <p role="alert" className="mt-2 text-sm text-red-700">{poError}</p>}
        {poSuccess && <p role="status" className="mt-2 text-sm text-green-700">{poSuccess}</p>}
        <div className="mt-3">
          <button
            type="button"
            onClick={submitPo}
            disabled={poBusy}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {poBusy ? "Creating…" : "Create draft PO"}
          </button>
        </div>

        <h3 className="mt-5 text-sm font-semibold text-gray-900">Open drafts ({draftOrders.length})</h3>
        {draftOrders.length === 0 ? (
          <p className="mt-1 text-sm text-gray-500">No open purchase orders.</p>
        ) : (
          <ul className="mt-2 divide-y divide-gray-100">
            {draftOrders.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <span className="text-gray-700">
                  <span className="font-semibold text-gray-900">PO #{o.id}</span> · {o.quantity} units of {o.product_id} for {o.store_id}
                  {o.note ? <span className="text-gray-500"> — {o.note}</span> : null}
                </span>
                <span className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => handleReceive(o.id)}
                    disabled={poActionId === o.id}
                    className="rounded-md bg-green-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-green-700 disabled:opacity-50"
                  >
                    {poActionId === o.id ? "Receiving…" : "Mark received (DELIVERY)"}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleCancel(o.id)}
                    disabled={poActionId === o.id}
                    className="rounded-md border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                  >
                    Cancel
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}

        {pastOrders.length > 0 && (
          <>
            <h3 className="mt-5 text-sm font-semibold text-gray-900">Recent history</h3>
            <ul className="mt-2 divide-y divide-gray-100">
              {pastOrders.map((o) => (
                <li key={o.id} className="py-1.5 text-sm text-gray-600">
                  PO #{o.id} · {o.quantity} units of {o.product_id} for {o.store_id} ·{" "}
                  <span className={`font-semibold ${o.status === "RECEIVED" ? "text-green-700" : "text-gray-500"}`}>{o.status}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <p className="text-xs text-gray-400">
        Lead time and safety-stock assumptions are documented in docs/limitations.md — this dataset has no real
        supplier lead time, so a configurable default is used and disclosed on every calculation.
      </p>
    </div>
  );
}
