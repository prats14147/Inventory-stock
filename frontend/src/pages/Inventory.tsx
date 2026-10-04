// frontend/src/pages/Inventory.tsx

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import {
  ApiError,
  adjustInventory,
  getCurrentInventory,
  getStockMovements,
  saveInventory,
} from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import PinButton from "../components/PinButton";

const CATEGORIES = [
  "Furniture",
  "Toys",
  "Clothing",
  "Groceries",
  "Electronics",
];

const REGIONS = ["North", "South", "East", "West"];
const PAGE_SIZE = 20;

type SortKey =
  | "product_id"
  | "category"
  | "region"
  | "store_id"
  | "inventory_level"
  | "units_ordered";

type SortDir = "asc" | "desc";

const COLUMNS: Array<{
  key: SortKey;
  label: string;
  numeric?: boolean;
}> = [
  { key: "product_id", label: "Product" },
  { key: "category", label: "Category" },
  { key: "region", label: "Region" },
  { key: "store_id", label: "Store" },
  { key: "inventory_level", label: "Stock on Hand", numeric: true },
  { key: "units_ordered", label: "Units Ordered", numeric: true },
];

const MOVEMENT_TYPES = [
  "SALE",
  "DELIVERY",
  "RETURN",
  "MANUAL_CORRECTION",
];

export default function Inventory() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlProduct = searchParams.get("product") ?? "";

  const [category, setCategory] = useState("");
  const [productFilter, setProductFilter] = useState(urlProduct);
  const [storeFilter, setStoreFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "low">("all");
  const [movementTypeFilter, setMovementTypeFilter] = useState("");

  const [refreshKey, setRefreshKey] = useState(0);
  const [formOpen, setFormOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const [movementType, setMovementType] = useState<
    "DELIVERY" | "RETURN" | "MANUAL_CORRECTION"
  >("DELIVERY");

  const [quantityDelta, setQuantityDelta] = useState("");
  const [movementReason, setMovementReason] = useState("");

  const [form, setForm] = useState({
    product_id: "",
    store_id: "",
    inventory_level: "",
    units_ordered: "0",
    category: "",
    region: "",
  });

  // Deep link (?product=P0001) wins on arrival and whenever the URL changes.
  // This is how chat answer cards and the watchlist hand off to this page.
  useEffect(() => {
    setProductFilter(urlProduct);
  }, [urlProduct]);

  function changeProduct(next: string) {
    setProductFilter(next);

    const params = new URLSearchParams(searchParams);

    if (next) {
      params.set("product", next);
    } else {
      params.delete("product");
    }

    setSearchParams(params, { replace: true });
  }

  // -------------------------------------------------------------------------
  // Current inventory
  // -------------------------------------------------------------------------

  const {
    data,
    loading,
    error,
  } = useApi(
    () => getCurrentInventory({ category: category || undefined }),
    [category, refreshKey]
  );

  // -------------------------------------------------------------------------
  // Stock movement history
  // -------------------------------------------------------------------------

  const {
    data: movements,
    loading: movementsLoading,
    error: movementsError,
  } = useApi(
    () =>
      getStockMovements({
        product_id: productFilter || undefined,
        store_id: storeFilter || undefined,
        movement_type: movementTypeFilter || undefined,
      }),
    [productFilter, storeFilter, movementTypeFilter, refreshKey]
  );

  // -------------------------------------------------------------------------
  // Form helpers
  // -------------------------------------------------------------------------

  function resetMovementFields() {
    setMovementType("DELIVERY");
    setQuantityDelta("");
    setMovementReason("");
  }

  function beginAdd() {
    setForm({
      product_id: "",
      store_id: "",
      inventory_level: "",
      units_ordered: "0",
      category: "",
      region: "",
    });

    resetMovementFields();
    setFormError("");
    setSuccessMessage("");
    setFormOpen(true);
  }

  function beginEdit(row: NonNullable<typeof data>[number]) {
    setForm({
      product_id: row.product_id,
      store_id: row.store_id,
      inventory_level: String(row.inventory_level),
      units_ordered: String(row.units_ordered),
      category: CATEGORIES.includes(row.category) ? row.category : "",
      region: REGIONS.includes(row.region) ? row.region : "",
    });

    resetMovementFields();
    setFormError("");
    setSuccessMessage("");
    setFormOpen(true);
  }

  // Check whether the product/store entered in the form already exists.
  const existingFormRow = useMemo(() => {
    const productId = form.product_id.trim();
    const storeId = form.store_id.trim();

    if (!productId || !storeId) {
      return undefined;
    }

    return data?.find(
      (row) =>
        row.product_id === productId &&
        row.store_id === storeId
    );
  }, [data, form.product_id, form.store_id]);

  async function submitInventory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setSaving(true);
    setFormError("");
    setSuccessMessage("");

    try {
      const productId = form.product_id.trim();
      const storeId = form.store_id.trim();

      if (!productId || !storeId) {
        throw new Error("Product ID and Store ID are required.");
      }

      // ---------------------------------------------------------------
      // Existing product/store = record a stock movement
      // ---------------------------------------------------------------

      if (existingFormRow) {
        const delta = Number(quantityDelta);

        if (!Number.isInteger(delta) || delta === 0) {
          throw new Error(
            "Quantity change must be a non-zero whole number."
          );
        }

        if (
          (movementType === "DELIVERY" || movementType === "RETURN") &&
          delta <= 0
        ) {
          throw new Error(
            "Delivery and Return quantities must be positive."
          );
        }

        if (!movementReason.trim()) {
          throw new Error(
            "Please enter a reason for this stock movement."
          );
        }

        const result = await adjustInventory({
          product_id: productId,
          store_id: storeId,
          movement_type: movementType,
          quantity_delta: delta,
          reason: movementReason.trim(),
        });

        setSuccessMessage(
          `${movementType.replace(
            "_",
            " "
          )} recorded for ${result.product_id} at ${
            result.store_id
          }: ${result.quantity_before} → ${result.quantity_after}.`
        );
      } else {
        // -------------------------------------------------------------
        // New product/store = create the starting inventory record
        // -------------------------------------------------------------

        if (!form.inventory_level.trim()) {
          throw new Error("Please enter the starting stock.");
        }

        if (!form.category) {
          throw new Error("Please select a category.");
        }

        if (!form.region) {
          throw new Error("Please select a region.");
        }

        const result = await saveInventory({
          product_id: productId,
          store_id: storeId,
          inventory_level: Number(form.inventory_level),
          units_ordered: Number(form.units_ordered),
          category: form.category,
          region: form.region,
        });

        setSuccessMessage(
          `${result.created ? "Stock record added" : "Stock updated"} for ${
            result.product_id
          } at ${result.store_id}.`
        );
      }

      setFormOpen(false);
      resetMovementFields();
      setRefreshKey((key) => key + 1);
    } catch (err) {
      setFormError(
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "Could not save this stock record. Please try again."
      );
    } finally {
      setSaving(false);
    }
  }

  // -------------------------------------------------------------------------
  // Inventory filtering
  // -------------------------------------------------------------------------

  const rows = useMemo(() => {
    let filtered = data ?? [];

    if (productFilter) {
      filtered = filtered.filter(
        (r) => r.product_id === productFilter
      );
    }

    if (storeFilter) {
      filtered = filtered.filter(
        (r) => r.store_id === storeFilter
      );
    }

    if (statusFilter === "low") {
      filtered = filtered.filter(
        (r) => r.inventory_level < 50
      );
    }

    return filtered;
  }, [data, productFilter, storeFilter, statusFilter]);

  // -------------------------------------------------------------------------
  // Inventory sorting and pagination
  // -------------------------------------------------------------------------

  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] =
    useState<SortKey>("product_id");
  const [sortDir, setSortDir] =
    useState<SortDir>("asc");
  const [page, setPage] = useState(1);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) =>
        d === "asc" ? "desc" : "asc"
      );
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

      if (
        typeof av === "number" &&
        typeof bv === "number"
      ) {
        return (av - bv) * dir;
      }

      return (
        String(av).localeCompare(String(bv)) * dir
      );
    });
  }, [rows, search, sortKey, sortDir]);

  const pageCount = Math.max(
    1,
    Math.ceil(sorted.length / PAGE_SIZE)
  );

  // A filter change can leave us past the last page; clamp rather than blank.
  const currentPage = Math.min(page, pageCount);

  const paged = sorted.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE
  );

  const productIds = useMemo(
    () =>
      Array.from(
        new Set(
          (data ?? []).map((r) => r.product_id)
        )
      ).sort(),
    [data]
  );

  const storeIds = useMemo(
    () =>
      Array.from(
        new Set(
          (data ?? []).map((r) => r.store_id)
        )
      ).sort(),
    [data]
  );

  // -------------------------------------------------------------------------
  // Stock movement helpers
  // -------------------------------------------------------------------------

  function movementLabel(type: string) {
    switch (type) {
      case "SALE":
        return "Sale";
      case "DELIVERY":
        return "Delivery";
      case "RETURN":
        return "Return";
      case "MANUAL_CORRECTION":
        return "Manual Correction";
      default:
        return type;
    }
  }

  function formatMovementDate(value: string) {
    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleString();
  }

  function movementBadgeClass(type: string) {
    switch (type) {
      case "SALE":
        return "bg-red-100 text-red-800 ring-red-600/20";

      case "DELIVERY":
        return "bg-blue-100 text-blue-800 ring-blue-600/20";

      case "RETURN":
        return "bg-green-100 text-green-800 ring-green-600/20";

      case "MANUAL_CORRECTION":
        return "bg-amber-100 text-amber-800 ring-amber-600/20";

      default:
        return "bg-gray-100 text-gray-800 ring-gray-600/20";
    }
  }

  // -------------------------------------------------------------------------
  // Page
  // -------------------------------------------------------------------------

  return (
    <div className="space-y-4">
      <PageHeader
        title="Inventory"
        subtitle={
          search
            ? `${sorted.length} of ${rows.length} rows match “${search}”. Low means under 50 units.`
            : `${sorted.length} of ${
                (data ?? []).length
              } store-product combinations shown. Low means under 50 units.`
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-brand-100 bg-brand-50 px-4 py-3">
        <p className="text-sm text-gray-700">
          Add a new product with starting stock, or record a
          delivery, return, or manual correction for an existing
          product.
        </p>

        <button
          type="button"
          onClick={beginAdd}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-700"
        >
          Add product / stock
        </button>
      </div>

      {successMessage && (
        <p
          role="status"
          className="rounded-lg bg-green-50 px-4 py-3 text-sm text-green-800"
        >
          {successMessage}
        </p>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Add / edit stock form                                               */}
      {/* ------------------------------------------------------------------ */}

      {formOpen && (
        <Card>
          <form
            onSubmit={submitInventory}
            className="space-y-4"
          >
            <div>
              <h2 className="text-base font-semibold text-gray-900">
                {existingFormRow
                  ? "Record stock movement"
                  : "Add new product / stock"}
              </h2>

              <p className="mt-1 text-sm text-gray-500">
                {existingFormRow
                  ? "This product already exists. Choose the type of stock movement, enter the quantity change, and explain why the stock changed."
                  : "Enter the product and store information together with its starting stock."}
              </p>
            </div>

            {/* Product and store */}
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-sm font-medium text-gray-700">
                Product ID

                <input
                  required
                  maxLength={20}
                  value={form.product_id}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      product_id: e.target.value,
                    })
                  }
                  placeholder="e.g. P0021"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal"
                />
              </label>

              <label className="space-y-1 text-sm font-medium text-gray-700">
                Store ID

                <input
                  required
                  maxLength={20}
                  value={form.store_id}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      store_id: e.target.value                    })
                  }
                  placeholder="e.g. S0001"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal"
                />
              </label>
            </div>

            {/* ------------------------------------------------------------ */}
            {/* New product fields                                            */}
            {/* ------------------------------------------------------------ */}

            {!existingFormRow && (
              <>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <label className="space-y-1 text-sm font-medium text-gray-700">
                    Starting Stock

                    <input
                      required
                      type="number"
                      min="0"
                      step="1"
                      value={form.inventory_level}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          inventory_level:
                            e.target.value,
                        })
                      }
                      placeholder="e.g. 100"
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal"
                    />
                  </label>

                  <label className="space-y-1 text-sm font-medium text-gray-700">
                    Units Ordered

                    <input
                      required
                      type="number"
                      min="0"
                      step="1"
                      value={form.units_ordered}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          units_ordered:
                            e.target.value,
                        })
                      }
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal"
                    />
                  </label>

                  <label className="space-y-1 text-sm font-medium text-gray-700">
                    Category

                    <select
                      required
                      value={form.category}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          category: e.target.value,
                        })
                      }
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-normal"
                    >
                      <option value="" disabled>
                        Select a category
                      </option>

                      {CATEGORIES.map((item) => (
                        <option
                          key={item}
                          value={item}
                        >
                          {item}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="space-y-1 text-sm font-medium text-gray-700">
                    Region

                    <select
                      required
                      value={form.region}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          region: e.target.value,
                        })
                      }
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-normal"
                    >
                      <option value="" disabled>
                        Select a region
                      </option>

                      {REGIONS.map((item) => (
                        <option
                          key={item}
                          value={item}
                        >
                          {item}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className="rounded-lg bg-gray-50 px-4 py-3 text-sm text-gray-600">
                  <strong>New product:</strong> Starting
                  stock is the initial quantity currently
                  available. It will not create a movement
                  history entry.
                </div>
              </>
            )}

            {/* ------------------------------------------------------------ */}
            {/* Existing product movement fields                              */}
            {/* ------------------------------------------------------------ */}

            {existingFormRow && (
              <>
                <div className="rounded-lg border border-brand-100 bg-brand-50 px-4 py-3 text-sm text-gray-700">
                  <strong>Current stock:</strong>{" "}
                  {existingFormRow.inventory_level} units
                </div>

                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <label className="space-y-1 text-sm font-medium text-gray-700">
                    Movement Type

                    <select
                      required
                      value={movementType}
                      onChange={(e) =>
                        setMovementType(
                          e.target.value as
                            | "DELIVERY"
                            | "RETURN"
                            | "MANUAL_CORRECTION"
                        )
                      }
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-normal"
                    >
                      <option value="DELIVERY">
                        Delivery
                      </option>

                      <option value="RETURN">
                        Return
                      </option>

                      <option value="MANUAL_CORRECTION">
                        Manual Correction
                      </option>
                    </select>
                  </label>

                  <label className="space-y-1 text-sm font-medium text-gray-700">
                    Quantity Change

                    <input
                      required
                      type="number"
                      step="1"
                      value={quantityDelta}
                      onChange={(e) =>
                        setQuantityDelta(
                          e.target.value
                        )
                      }
                      placeholder={
                        movementType ===
                        "MANUAL_CORRECTION"
                          ? "e.g. -5 or 10"
                          : "e.g. 10"
                      }
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal"
                    />

                    <span className="block text-xs font-normal text-gray-500">
                      {movementType ===
                      "MANUAL_CORRECTION"
                        ? "Use + or - to correct the stock."
                        : "Enter a positive number of units."}
                    </span>
                  </label>

                  <label className="space-y-1 text-sm font-medium text-gray-700">
                    Reason

                    <input
                      required
                      type="text"
                      maxLength={500}
                      value={movementReason}
                      onChange={(e) =>
                        setMovementReason(
                          e.target.value
                        )
                      }
                      placeholder={
                        movementType === "DELIVERY"
                          ? "e.g. Supplier delivery"
                          : movementType === "RETURN"
                          ? "e.g. Customer returned items"
                          : "e.g. Damaged stock correction"
                      }
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal"
                    />
                  </label>
                </div>

                <div className="rounded-lg bg-gray-50 px-4 py-3 text-sm text-gray-600">
                  <strong>History:</strong> This change will
                  be saved with the movement type, reason,
                  quantity before, quantity after, and
                  timestamp.
                </div>
              </>
            )}

            {formError && (
              <p
                role="alert"
                className="text-sm text-red-700"
              >
                {formError}
              </p>
            )}

            <div className="flex gap-2">
              <button
                disabled={saving}
                type="submit"
                className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {saving
                  ? "Saving…"
                  : existingFormRow
                  ? "Record movement"
                  : "Add product"}
              </button>

              <button
                type="button"
                onClick={() => {
                  setFormOpen(false);
                  resetMovementFields();
                  setFormError("");
                }}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </form>
        </Card>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Current inventory                                                   */}
      {/* ------------------------------------------------------------------ */}

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
            onChange={(e) =>
              setCategory(e.target.value)
            }
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
            onChange={(e) =>
              changeProduct(e.target.value)
            }
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
            onChange={(e) =>
              setStoreFilter(e.target.value)
            }
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
            onChange={(e) =>
              setStatusFilter(
                e.target.value as "all" | "low"
              )
            }
            aria-label="Filter by stock status"
            >  
            <option value="all">
              All stock levels
            </option>

            <option value="low">
              Low stock only (&lt; 50)
            </option>
          </select>
        </div>

        {loading && (
          <LoadingState label="Loading inventory..." />
        )}

        {error && <ErrorState message={error} />}

        {!loading && !error && (
          <>
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    {COLUMNS.map((col) => (
                      <th
                        key={col.key}
                        className="whitespace-nowrap px-4 py-2.5 text-left"
                      >
                        <button
                          type="button"
                          onClick={() =>
                            toggleSort(col.key)
                          }
                          className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-gray-500 hover:text-gray-800"
                          aria-label={`Sort by ${col.label}`}
                        >
                          {col.label}

                          <span
                            aria-hidden="true"
                            className={
                              sortKey === col.key
                                ? "text-brand-600"
                                : "text-gray-300"
                            }
                          >
                            {sortKey === col.key
                              ? sortDir === "asc"
                                ? "▲"
                                : "▼"
                              : "↕"}
                          </span>
                        </button>
                      </th>
                    ))}

                    {["Status", "Actions"].map(
                      (h) => (
                        <th
                          key={h}
                          className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500"
                        >
                          {h}
                        </th>
                      )
                    )}
                  </tr>
                </thead>

                <tbody className="divide-y divide-gray-100">
                  {paged.map((r) => (
                    <tr
                      key={`${r.store_id}-${r.product_id}`}
                      className="transition-colors hover:bg-brand-50/50"
                    >
                      <td className="whitespace-nowrap px-4 py-2 font-medium text-gray-900">
                        {r.product_id}
                      </td>

                      <td className="whitespace-nowrap px-4 py-2 text-gray-600">
                        {r.category}
                      </td>

                      <td className="whitespace-nowrap px-4 py-2 text-gray-600">
                        {r.region}
                      </td>

                      <td className="whitespace-nowrap px-4 py-2 text-gray-600">
                        {r.store_id}
                      </td>

                      <td className="whitespace-nowrap px-4 py-2 tabular-nums text-gray-900">
                        {r.inventory_level}
                      </td>

                      <td className="whitespace-nowrap px-4 py-2 tabular-nums text-gray-600">
                        {r.units_ordered}
                      </td>

                      <td className="whitespace-nowrap px-4 py-2">
                        {r.inventory_level < 50 ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800 ring-1 ring-inset ring-amber-600/20">
                            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                            Low
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-800 ring-1 ring-inset ring-green-600/20">
                            <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                            OK
                          </span>
                        )}
                </td>

                      <td className="whitespace-nowrap px-4 py-2 text-right">
                        <button
                          type="button"
                          onClick={() =>
                            beginEdit(r)
                          }
                          className="mr-2 rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
                        >
                          Edit stock
                        </button>

                        <PinButton
                          productId={r.product_id}
                        />
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
                  hint="Try widening the filters — e.g. clear the search box, the product filter, or the low-stock-onlyilter."
                />
              </div>
            )}

            {sorted.length > PAGE_SIZE && (
              <nav
                className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm"
                aria-label="Inventory pages"
              >
                <span className="text-gray-500">
                  Showing{" "}
                  {(currentPage - 1) *
                    PAGE_SIZE +
                    1}
                  –
                  {Math.min(
                    currentPage * PAGE_SIZE,
                    sorted.length
                  )}{" "}
                  of {sorted.length} rows
                </span>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      setPage((p) =>
                        Math.max(1, p - 1)
                      )
                    }
                    disabled={currentPage === 1}
                    className="rounded-lg border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    ← Previous
                  </button>

                  <span className="tabular-nums text-gray-600">
                    Page {currentPage} of{" "}
                    {pageCount}
                  </span>

                  <button
                    type="button"
                    onClick={() =>
                      setPage((p) =>
                        Math.min(
                          pageCount,
                          p + 1
                        )
                      )
                    }
                    disabled={
                      currentPage === pageCount
                    }
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

      {/* ------------------------------------------------------------------ */}
      {/* Stock movement history                                              */}
      {/* ------------------------------------------------------------------ */}

      <Card>
        <div className="mb-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-gray-900">
                Stock Movement History
              </h2>

              <p className="mt-1 text-sm text-gray-500">
                Every recorded sale, delivery, return,
                and manual stock correction is kept here
                with the stock before and after the
                change.
              </p>
            </div>

            <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-600">
              {movements?.length ?? 0} movements
            </span>
          </div>
        </div>

        <div className="mb-4 flex flex-wrap gap-2">
          <select
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none"
            value={movementTypeFilter}
            onChange={(e) =>
              setMovementTypeFilter(
                e.target.value
              )
            }
            aria-label="Filter by movement type"
          >
            <option value="">
              All movement types
            </option>

            {MOVEMENT_TYPES.map((type) => (
              <option key={type} value={type}>
                {movementLabel(type)}
              </option>
            ))}
          </select>

          <span className="flex items-center rounded-lg bg-gray-50 px-3 py-1.5 text-xs text-gray-500">
            Product: {productFilter || "All"}
          </span>

          <span className="flex items-center rounded-lg bg-gray-50 px-3 py-1.5 text-xs text-gray-500">
            Store: {storeFilter || "All"}
          </span>
        </div>

        {movementsLoading && (
          <LoadingState label="Loading stock movement history..." />
        )}

        {movementsError && (
          <ErrorState message={movementsError} />
        )}

        {!movementsLoading && !movementsError && (
          <>
            {!movements ||
            movements.length === 0 ? (
              <EmptyState
                title="No stock movements found."
                hint="Sales, deliveries, returns, and stock corrections will appear here when they are recorded."
              />
            ) : (
              <div className="overflow-x-auto rounded-lg border border-gray-200">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                        Date / Time
                      </th>

                      <th className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                        Type
                      </th>

                      <th className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                        Product
                      </th>

                      <th className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                        Store
                      </th>

                      <th className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                        Change
                      </th>

                      <th className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                        Before → After
                      </th>

                      <th className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                        Reason
                      </th>
                    </tr>
                  </thead>

                  <tbody className="divide-y divide-gray-100">
                    {movements.map(
                      (movement) => (
                        <tr
                          key={movement.id}
                          className="transition-colors hover:bg-brand-50/50"
                        >
                          <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                            {formatMovementDate(
                              movement.occurred_at
                            )}
                          </td>

                          <td className="whitespace-nowrap px-4 py-3">
                            <span
                              className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${movementBadgeClass(
                                movement.movement_type
                              )}`}
                            >
                              {movementLabel(
                                movement.movement_type
                              )}
                            </span>
                          </td>

                          <td className="whitespace-nowrap px-4 py-3 font-medium text-gray-900">
                            {movement.product_id}
                          </td>

                          <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                            {movement.store_id}
                          </td>

                          <td className="whitespace-nowrap px-4 py-3 font-semibold tabular-nums">
                            <span
                              className={
                                movement.quantity_delta >
                                0
                                  ? "text-green-700"
                                  : "text-red-700"
                              }
                            >
                              {movement.quantity_delta >
                              0
                                ? "+"
                                : ""}
                              {
                                movement.quantity_delta
                              }
                            </span>
                          </td>

                          <td className="whitespace-nowrap px-4 py-3 tabular-nums text-gray-900">
                            {
                              movement.quantity_before
                            }{" "}
                            →{" "}
                            {
                              movement.quantity_after
                            }
                          </td>

                          <td className="min-w-48 px-4 py-3 text-gray-600">
                            {movement.reason}
                          </td>
                        </tr>
                      )
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
