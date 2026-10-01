// frontend/src/pages/Inventory.tsx

import { useMemo, useState } from "react";
import { useApi } from "../hooks/useApi";
import { getCurrentInventory } from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";

const CATEGORIES = ["Furniture", "Toys", "Clothing", "Groceries", "Electronics"];

export default function Inventory() {
  const [category, setCategory] = useState("");
  const [productFilter, setProductFilter] = useState("");
  const [storeFilter, setStoreFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "low">("all");

  const { data, loading, error } = useApi(() => getCurrentInventory({ category: category || undefined }), [category]);

  const rows = useMemo(() => {
    let filtered = data ?? [];
    if (productFilter) filtered = filtered.filter((r) => r.product_id === productFilter);
    if (storeFilter) filtered = filtered.filter((r) => r.store_id === storeFilter);
    if (statusFilter === "low") filtered = filtered.filter((r) => r.inventory_level < 50);
    return filtered;
  }, [data, productFilter, storeFilter, statusFilter]);

  const productIds = useMemo(() => Array.from(new Set((data ?? []).map((r) => r.product_id))).sort(), [data]);
  const storeIds = useMemo(() => Array.from(new Set((data ?? []).map((r) => r.store_id))).sort(), [data]);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Inventory</h1>

      <div className="flex flex-wrap gap-3">
        <select className="rounded-md border px-3 py-1.5 text-sm" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select className="rounded-md border px-3 py-1.5 text-sm" value={productFilter} onChange={(e) => setProductFilter(e.target.value)}>
          <option value="">All products</option>
          {productIds.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <select className="rounded-md border px-3 py-1.5 text-sm" value={storeFilter} onChange={(e) => setStoreFilter(e.target.value)}>
          <option value="">All stores</option>
          {storeIds.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          className="rounded-md border px-3 py-1.5 text-sm"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as "all" | "low")}
        >
          <option value="all">All stock levels</option>
          <option value="low">Low stock only (&lt; 50)</option>
        </select>
      </div>

      {loading && <LoadingState label="Loading inventory..." />}
      {error && <ErrorState message={error} />}

      {!loading && !error && (
        <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                {["Product", "Category", "Store", "Region", "Inventory", "Units Ordered", "Status"].map((h) => (
                  <th key={h} className="px-4 py-2 text-left font-medium text-gray-500">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.map((r) => (
                <tr key={`${r.store_id}-${r.product_id}`}>
                  <td className="px-4 py-2">{r.product_id}</td>
                  <td className="px-4 py-2">{r.category}</td>
                  <td className="px-4 py-2">{r.store_id}</td>
                  <td className="px-4 py-2">{r.region}</td>
                  <td className="px-4 py-2">{r.inventory_level}</td>
                  <td className="px-4 py-2">{r.units_ordered}</td>
                  <td className="px-4 py-2">
                    {r.inventory_level < 50 ? (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">Low</span>
                    ) : (
                      <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-800">OK</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <p className="p-4 text-center text-gray-500">No matching rows.</p>}
        </div>
      )}
    </div>
  );
}
