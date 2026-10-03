// frontend/src/pages/Inventory.tsx

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { getCurrentInventory } from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import PinButton from "../components/PinButton";

const CATEGORIES = ["Furniture", "Toys", "Clothing", "Groceries", "Electronics"];
const PAGE_SIZE = 20;

type SortKey = "product_id" | "category" | "store_id" | "inventory_level" | "units_ordered";
type SortDir = "asc" | "desc";

const COLUMNS: Array<{ key: SortKey; label: string; numeric?: boolean }> = [
  { key: "product_id", label: "Product" },
  { key: "category", label: "Category" },
  { key: "store_id", label: "Store" },
  { key: "inventory_level", label: "Inventory", numeric: true },
  { key: "units_ordered", label: "Units Ordered", numeric: true },
];

export default function Inventory() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlProduct = searchParams.get("product") ?? "";
  const [category, setCategory] = useState("");
  const [productFilter, setProductFilter] = useState(urlProduct);
  const [storeFilter, setStoreFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "low">("all");

  // Deep link (?product=P0001) wins on arrival and whenever the URL changes --
  // that is how the chat answer cards and the watchlist hand off to this page.
  useEffect(() => {
    setProductFilter(urlProduct);
  }, [urlProduct]);

  function changeProduct(next: string) {
    setProductFilter(next);
    const params = new URLSearchParams(searchParams);
    if (next) params.set("product", next);
    else params.delete("product");
    setSearchParams(params, { replace: true });
  }

  const { data, loading, error } = useApi(() => getCurrentInventory({ category: category || undefined }), [category]);

  const rows = useMemo(() => {
    let filtered = data ?? [];
    if (productFilter) filtered = filtered.filter((r) => r.product_id === productFilter);
    if (storeFilter) filtered = filtered.filter((r) => r.store_id === storeFilter);
    if (statusFilter === "low") filtered = filtered.filter((r) => r.inventory_level < 50);
    return filtered;
  }, [data, productFilter, storeFilter, statusFilter]);

  // --- Tier A: text search, sortable columns, 20 rows per page -------------
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("product_id");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [page, setPage] = useState(1);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
    setPage(1);
  }

  const sorted = useMemo(() => {
    const filtered = rows.filter((r) => {
      if (!search) return true;
      const q = search.toLowerCase();
      return (
        r.product_id.toLowerCase().includes(q) ||
        r.category.toLowerCase().includes(q) ||
        r.store_id.toLowerCase().includes(q) ||
        r.region.toLowerCase().includes(q)
      );
    });
    const dir = sortDir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [rows, search, sortKey, sortDir]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  // A filter change can leave us past the last page; clamp rather than blank.
  const currentPage = Math.min(page, pageCount);
  const paged = sorted.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);


  const productIds = useMemo(() => Array.from(new Set((data ?? []).map((r) => r.product_id))).sort(), [data]);
  const storeIds = useMemo(() => Array.from(new Set((data ?? []).map((r) => r.store_id))).sort(), [data]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Inventory"
        subtitle={
          search
            ? `${sorted.length} of ${rows.length} rows match “${search}”. Low means under 50 units.`
            : `${sorted.length} of ${(data ?? []).length} store-product combinations shown. Low means under 50 units.`
        }
      />

      <Card>
        <div className="mb-4 flex flex-wrap gap-2">
          <input
            type="search"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search product, category, store, region..."
            className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none sm:w-64"
            aria-label="Search inventory rows"
          />
          <select
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            aria-label="Filter by category"
          >
            <option value="">All categories</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <select
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none"
            value={productFilter}
            onChange={(e) => changeProduct(e.target.value)}
            aria-label="Filter by product"
          >
            <option value="">All products</option>
            {productIds.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <select
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none"
            value={storeFilter}
            onChange={(e) => setStoreFilter(e.target.value)}
            aria-label="Filter by store"
          >
            <option value="">All stores</option>
            {storeIds.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as "all" | "low")}
            aria-label="Filter by stock status"
          >
            <option value="all">All stock levels</option>
            <option value="low">Low stock only (&lt; 50)</option>
          </select>
        </div>

        {loading && <LoadingState label="Loading inventory..." />}
        {error && <ErrorState message={error} />}

        {!loading && !error && (
          <>
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    {COLUMNS.map((col) => (
                      <th key={col.key} className="whitespace-nowrap px-4 py-2.5 text-left">
                        <button
                          type="button"
                          onClick={() => toggleSort(col.key)}
                          className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-gray-500 hover:text-gray-800"
                          aria-label={`Sort by ${col.label}`}
                        >
                          {col.label}
                          <span aria-hidden="true" className={sortKey === col.key ? "text-brand-600" : "text-gray-300"}>
                            {sortKey === col.key ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
                          </span>
                        </button>
                      </th>
                    ))}
                    {["Region", "Status", ""].map((h) => (
                      <th key={h} className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {paged.map((r) => (
                    <tr key={`${r.store_id}-${r.product_id}`} className="transition-colors hover:bg-brand-50/50">
                      <td className="whitespace-nowrap px-4 py-2 font-medium text-gray-900">{r.product_id}</td>
                      <td className="whitespace-nowrap px-4 py-2 text-gray-600">{r.category}</td>
                      <td className="whitespace-nowrap px-4 py-2 text-gray-600">{r.store_id}</td>
                      <td className="whitespace-nowrap px-4 py-2 text-gray-600">{r.region}</td>
                      <td className="whitespace-nowrap px-4 py-2 tabular-nums text-gray-900">{r.inventory_level}</td>
                      <td className="whitespace-nowrap px-4 py-2 tabular-nums text-gray-600">{r.units_ordered}</td>
                      <td className="whitespace-nowrap px-4 py-2">
                        {r.inventory_level < 50 ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800 ring-1 ring-inset ring-amber-600/20">
                            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" /> Low
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-800 ring-1 ring-inset ring-green-600/20">
                            <span className="h-1.5 w-1.5 rounded-full bg-green-500" /> OK
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2 text-right">
                        <PinButton productId={r.product_id} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {sorted.length === 0 && (
              <div className="mt-3">
                <EmptyState
                  title="No matching rows."
                  hint="Try widening the filters — e.g. clear the search box, the product filter, or the low-stock-only filter."
                />
              </div>
            )}

            {sorted.length > PAGE_SIZE && (
              <nav className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm" aria-label="Inventory pages">
                <span className="text-gray-500">
                  Showing {(currentPage - 1) * PAGE_SIZE + 1}–
                  {Math.min(currentPage * PAGE_SIZE, sorted.length)} of {sorted.length} rows
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="rounded-lg border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    ← Previous
                  </button>
                  <span className="tabular-nums text-gray-600">
                    Page {currentPage} of {pageCount}
                  </span>
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                    disabled={currentPage === pageCount}
                    className="rounded-lg border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Next →
                  </button>
                </div>
              </nav>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
