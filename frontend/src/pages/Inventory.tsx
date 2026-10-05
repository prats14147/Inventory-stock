import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useApi } from "../hooks/useApi";

import {
  ApiError,
  adjustInventory,
  getCurrentInventory,
  getProducts,
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

const FAVORITE_ROWS_STORAGE_KEY =
  "inventory:selectedFavoriteRows";

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
  {
    key: "inventory_level",
    label: "Stock on Hand",
    numeric: true,
  },
  {
    key: "units_ordered",
    label: "Units Ordered",
    numeric: true,
  },
];

const MOVEMENT_TYPES = [
  "SALE",
  "DELIVERY",
  "RETURN",
  "MANUAL_CORRECTION",
];

export default function Inventory() {
  const [searchParams, setSearchParams] =
    useSearchParams();

  const urlProduct =
    searchParams.get("product") ?? "";

  const [category, setCategory] =
    useState("");

  const [productFilter, setProductFilter] =
    useState(urlProduct);

  const [storeFilter, setStoreFilter] =
    useState("");

  const [statusFilter, setStatusFilter] =
    useState<"all" | "low">("all");

  const [movementTypeFilter, setMovementTypeFilter] =
    useState("");

  const [refreshKey, setRefreshKey] =
    useState(0);

  /*
   * Stores the exact Inventory row selected for each
   * pinned product.
   *
   * Example:
   *
   * {
   *   P0001: "P0001-S001",
   *   P0002: "P0002-S003"
   * }
   *
   * This is frontend-only state. The actual watchlist
   * remains product-level in the backend.
   */
  const [selectedFavoriteRows, setSelectedFavoriteRows] =
    useState<Record<string, string>>(() => {
      if (typeof window === "undefined") {
        return {};
      }

      try {
        const saved =
          window.sessionStorage.getItem(
            FAVORITE_ROWS_STORAGE_KEY
          );

        if (!saved) {
          return {};
        }

        const parsed: unknown =
          JSON.parse(saved);

        if (
          typeof parsed !== "object" ||
          parsed === null ||
          Array.isArray(parsed)
        ) {
          return {};
        }

        const result: Record<string, string> =
          {};

        for (const [productId, rowKey] of Object.entries(
          parsed
        )) {
          if (typeof rowKey === "string") {
            result[productId] = rowKey;
          }
        }

        return result;
      } catch {
        return {};
      }
    });

  const [formOpen, setFormOpen] =
    useState(false);

  const [saving, setSaving] =
    useState(false);

  const [formError, setFormError] =
    useState("");

  const [successMessage, setSuccessMessage] =
    useState("");

  const [movementType, setMovementType] =
    useState<
      "DELIVERY" |
      "RETURN" |
      "MANUAL_CORRECTION"
    >("DELIVERY");

  const [quantityDelta, setQuantityDelta] =
    useState("");

  const [movementReason, setMovementReason] =
    useState("");

  const [form, setForm] = useState({
    product_id: "",
    store_id: "",
    inventory_level: "",
    units_ordered: "0",
    region: "",
  });

  /*
   * Deep link:
   * /inventory?product=P0001
   */
  useEffect(() => {
    setProductFilter(urlProduct);
  }, [urlProduct]);

  /*
   * Persist the selected Inventory rows for this browser session.
   */
  useEffect(() => {
    try {
      window.sessionStorage.setItem(
        FAVORITE_ROWS_STORAGE_KEY,
        JSON.stringify(selectedFavoriteRows)
      );
    } catch {
      // Ignore storage errors.
    }
  }, [selectedFavoriteRows]);

  /*
   * Update the visually selected row for one product.
   */
  function handleFavoriteRowSelected(
    productId: string,
    rowKey: string | null
  ) {
    setSelectedFavoriteRows((previous) => {
      const next = {
        ...previous,
      };

      if (rowKey === null) {
        delete next[productId];
      } else {
        next[productId] = rowKey;
      }

      return next;
    });
  }

  function changeProduct(next: string) {
    setProductFilter(next);

    const params =
      new URLSearchParams(searchParams);

    if (next) {
      params.set("product", next);
    } else {
      params.delete("product");
    }

    setSearchParams(params, {
      replace: true,
    });
  }

  // -------------------------------------------------------------------------
  // Current inventory
  // -------------------------------------------------------------------------

  const {
    data,
    loading,
    error,
  } = useApi(
    () =>
      getCurrentInventory({
        category:
          category || undefined,
      }),
    [category, refreshKey]
  );

  // -------------------------------------------------------------------------
  // Product catalog
  // -------------------------------------------------------------------------

  const {
    data: productsData,
    loading: productsLoading,
    error: productsError,
  } = useApi(
    () => getProducts(),
    []
  );

  const productMap = useMemo(() => {
    const map = new Map<
      string,
      {
        product_id: string;
        name: string;
        sku: string;
        category: string;
      }
    >();

    for (
      const product of productsData?.products ?? []
    ) {
      map.set(
        product.product_id,
        product
      );
    }

    return map;
  }, [productsData]);

  function getProductName(
    productId: string
  ) {
    return (
      productMap.get(productId)?.name ??
      "Unknown product"
    );
  }

  function getProductSku(
    productId: string
  ) {
    return (
      productMap.get(productId)?.sku ??
      "—"
    );
  }

  function getProductCategory(
    productId: string,
    fallback: string
  ) {
    return (
      productMap.get(productId)?.category ??
      fallback
    );
  }

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
        product_id:
          productFilter || undefined,
        store_id:
          storeFilter || undefined,
        movement_type:
          movementTypeFilter || undefined,
      }),
    [
      productFilter,
      storeFilter,
      movementTypeFilter,
      refreshKey,
    ]
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
      region: "",
    });

    resetMovementFields();
    setFormError("");
    setSuccessMessage("");
    setFormOpen(true);
  }

  function beginEdit(
    row: NonNullable<typeof data>[number]
  ) {
    setForm({
      product_id: row.product_id,
      store_id: row.store_id,
      inventory_level:
        String(row.inventory_level),
      units_ordered:
        String(row.units_ordered),
      region: REGIONS.includes(row.region)
        ? row.region
        : "",
    });

    resetMovementFields();
    setFormError("");
    setSuccessMessage("");
    setFormOpen(true);
  }

  // -------------------------------------------------------------------------
  // Check whether the product/store already exists
  // -------------------------------------------------------------------------

  const existingFormRow = useMemo(() => {
    const productId =
      form.product_id.trim();

    const storeId =
      form.store_id.trim();

    if (!productId || !storeId) {
      return undefined;
    }

    return data?.find(
      (row) =>
        row.product_id === productId &&
        row.store_id === storeId
    );
  }, [
    data,
    form.product_id,
    form.store_id,
  ]);

  // -------------------------------------------------------------------------
  // Submit inventory form
  // -------------------------------------------------------------------------

  async function submitInventory(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    setSaving(true);
    setFormError("");
    setSuccessMessage("");

    try {
      const productId =
        form.product_id.trim();

      const storeId =
        form.store_id.trim();

      if (!productId || !storeId) {
        throw new Error(
          "Please select a product and enter a Store ID."
        );
      }

      // ---------------------------------------------------------------
      // Existing product/store = record a stock movement
      // ---------------------------------------------------------------

      if (existingFormRow) {
        const delta =
          Number(quantityDelta);

        if (
          !Number.isInteger(delta) ||
          delta === 0
        ) {
          throw new Error(
            "Quantity change must be a non-zero whole number."
          );
        }

        if (
          (movementType === "DELIVERY" ||
            movementType === "RETURN") &&
          delta <= 0
        ) {
          throw new Error(
            "Delivery and Return quantities must be positive."
          );
        }

        if (
          !movementReason.trim()
        ) {
          throw new Error(
            "Please enter a reason for this stock movement."
          );
        }

        const result =
          await adjustInventory({
            product_id: productId,
            store_id: storeId,
            movement_type:
              movementType,
            quantity_delta: delta,
            reason:
              movementReason.trim(),
          });

        setSuccessMessage(
          `${movementType.replace(
            "_",
            " "
          )} recorded for ${
            result.product_id
          } at ${
            result.store_id
          }: ${
            result.quantity_before
          } → ${
            result.quantity_after
          }.`
        );
      } else {
        // -------------------------------------------------------------
        // New product/store = create starting inventory record
        // -------------------------------------------------------------

        if (
          !productMap.has(productId)
        ) {
          throw new Error(
            "Please select a valid product from the product catalog."
          );
        }

        if (
          !form.inventory_level.trim()
        ) {
          throw new Error(
            "Please enter the starting stock."
          );
        }

        if (!form.region) {
          throw new Error(
            "Please select a region."
          );
        }

        const startingStock =
          Number(form.inventory_level);

        const unitsOrdered =
          Number(form.units_ordered);

        if (
          !Number.isInteger(
            startingStock
          ) ||
          startingStock < 0
        ) {
          throw new Error(
            "Starting stock must be a whole number of 0 or more."
          );
        }

        if (
          !Number.isInteger(
            unitsOrdered
          ) ||
          unitsOrdered < 0
        ) {
          throw new Error(
            "Units ordered must be a whole number of 0 or more."
          );
        }

        const result =
          await saveInventory({
            product_id: productId,
            store_id: storeId,
            inventory_level:
              startingStock,
            units_ordered:
              unitsOrdered,
            region:
              form.region,
          });

        setSuccessMessage(
          `${
            result.created
              ? "Stock record added"
              : "Stock updated"
          } for ${
            result.product_id
          } at ${
            result.store_id
          }.`
        );
      }

      setFormOpen(false);
      resetMovementFields();
      setRefreshKey(
        (key) => key + 1
      );
    } catch (err) {
      setFormError(
        err instanceof ApiError ||
          err instanceof Error
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
        (row) =>
          row.product_id ===
          productFilter
      );
    }

    if (storeFilter) {
      filtered = filtered.filter(
        (row) =>
          row.store_id ===
          storeFilter
      );
    }

    if (
      statusFilter === "low"
    ) {
      filtered = filtered.filter(
        (row) =>
          row.inventory_level < 50
      );
    }

    return filtered;
  }, [
    data,
    productFilter,
    storeFilter,
    statusFilter,
  ]);

  // -------------------------------------------------------------------------
  // Inventory sorting and pagination
  // -------------------------------------------------------------------------

  const [search, setSearch] =
    useState("");

  const [sortKey, setSortKey] =
    useState<SortKey>("product_id");

  const [sortDir, setSortDir] =
    useState<SortDir>("asc");

  const [page, setPage] =
    useState(1);

  function toggleSort(
    key: SortKey
  ) {
    if (key === sortKey) {
      setSortDir(
        (direction) =>
          direction === "asc"
            ? "desc"
            : "asc"
      );
    } else {
      setSortKey(key);
      setSortDir("asc");
    }

    setPage(1);
  }

  const sorted = useMemo(() => {
    const filtered =
      rows.filter((row) => {
        if (!search) {
          return true;
        }

        const q =
          search.toLowerCase();

        const product =
          productMap.get(
            row.product_id
          );

        return (
          row.product_id
            .toLowerCase()
            .includes(q) ||
          row.category
            .toLowerCase()
            .includes(q) ||
          row.store_id
            .toLowerCase()
            .includes(q) ||
          row.region
            .toLowerCase()
            .includes(q) ||
          product?.name
            .toLowerCase()
            .includes(q) ||
          product?.sku
            .toLowerCase()
            .includes(q) ||
          product?.category
            .toLowerCase()
            .includes(q)
        );
      });

    const dir =
      sortDir === "asc"
        ? 1
        : -1;

    return [...filtered].sort(
      (a, b) => {
        let av: string | number;
        let bv: string | number;

        if (
          sortKey ===
          "product_id"
        ) {
          av =
            productMap.get(
              a.product_id
            )?.name ??
            a.product_id;

          bv =
            productMap.get(
              b.product_id
            )?.name ??
            b.product_id;
        } else if (
          sortKey ===
          "category"
        ) {
          av =
            getProductCategory(
              a.product_id,
              a.category
            );

          bv =
            getProductCategory(
              b.product_id,
              b.category
            );
        } else {
          av = a[sortKey];
          bv = b[sortKey];
        }

        if (
          typeof av === "number" &&
          typeof bv === "number"
        ) {
          return (
            (av - bv) * dir
          );
        }

        return (
          String(av).localeCompare(
            String(bv)
          ) * dir
        );
      }
    );
  }, [
    rows,
    search,
    sortKey,
    sortDir,
    productMap,
  ]);

  const pageCount =
    Math.max(
      1,
      Math.ceil(
        sorted.length /
          PAGE_SIZE
      )
    );

  const currentPage =
    Math.min(
      page,
      pageCount
    );

  const paged =
    sorted.slice(
      (currentPage - 1) *
        PAGE_SIZE,
      currentPage *
        PAGE_SIZE
    );

  const storeIds = useMemo(
    () =>
      Array.from(
        new Set(
          (data ?? []).map(
            (row) =>
              row.store_id
          )
        )
      ).sort(),
    [data]
  );

  // -------------------------------------------------------------------------
  // Stock movement helpers
  // -------------------------------------------------------------------------

  function movementLabel(
    type: string
  ) {
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

  function formatMovementDate(
    value: string
  ) {
    const date =
      new Date(value);

    if (
      Number.isNaN(
        date.getTime()
      )
    ) {
      return value;
    }

    return date.toLocaleString();
  }

  function movementBadgeClass(
    type: string
  ) {
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
          Add stock for a catalog product, or
          record a delivery, return, or manual
          correction for an existing product.
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
            onSubmit={
              submitInventory
            }
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
                  : "Select a product from the catalog and enter its starting stock and store information."}
              </p>
            </div>

            {/* Product and store */}
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-sm font-medium text-gray-700">
                Product

                <select
                  required
                  value={
                    form.product_id
                  }
                  disabled={
                    productsLoading
                  }
                  onChange={(
                    event
                  ) =>
                    setForm({
                      ...form,
                      product_id:
                        event
                          .target
                          .value,
                    })
                  }
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-normal disabled:bg-gray-100"
                >
                  <option
                    value=""
                    disabled
                  >
                    {productsLoading
                      ? "Loading products..."
                      : "Select a product"}
                  </option>

                  {(
                    productsData?.products ??
                    []
                  ).map(
                    (
                      product
                    ) => (
                      <option
                        key={
                          product.product_id
                        }
                        value={
                          product.product_id
                        }
                      >
                        {
                          product.product_id
                        }{" "}
                        —{" "}
                        {
                          product.name
                        }{" "}
                        (
                        {
                          product.sku
                        }
                        )
                      </option>
                    )
                  )}
                </select>

                {form.product_id &&
                  productMap.has(
                    form.product_id
                  ) && (
                    <span className="block text-xs font-normal text-gray-500">
                      Category:{" "}
                      {
                        productMap.get(
                          form.product_id
                        )
                          ?.category
                      }
                    </span>
                  )}

                {productsError && (
                  <span className="block text-xs font-normal text-red-600">
                    Could not load the product
                    catalog.
                  </span>
                )}
              </label>

              <label className="space-y-1 text-sm font-medium text-gray-700">
                Store ID

                <input
                  required
                  maxLength={20}
                  value={
                    form.store_id
                  }
                  onChange={(
                    event
                  ) =>
                    setForm({
                      ...form,
                      store_id:
                        event
                          .target
                          .value,
                    })
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
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <label className="space-y-1 text-sm font-medium text-gray-700">
                    Starting Stock

                    <input
                      required
                      type="number"
                      min="0"
                      step="1"
                      value={
                        form.inventory_level
                      }
                      onChange={(
                        event
                      ) =>
                        setForm({
                          ...form,
                          inventory_level:
                            event
                              .target
                              .value,
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
                      value={
                        form.units_ordered
                      }
                      onChange={(
                        event
                      ) =>
                        setForm({
                          ...form,
                          units_ordered:
                            event
                              .target
                              .value,
                        })
                      }
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal"
                    />
                  </label>

                  <label className="space-y-1 text-sm font-medium text-gray-700">
                    Region

                    <select
                      required
                      value={
                        form.region
                      }
                      onChange={(
                        event
                      ) =>
                        setForm({
                          ...form,
                          region:
                            event
                              .target
                              .value,
                        })
                      }
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-normal"
                    >
                      <option
                        value=""
                        disabled
                      >
                        Select a region
                      </option>

                      {REGIONS.map(
                        (
                          item
                        ) => (
                          <option
                            key={item}
                            value={item}
                          >
                            {item}
                          </option>
                        )
                      )}
                    </select>
                  </label>
                </div>

                {form.product_id &&
                  productMap.has(
                    form.product_id
                  ) && (
                    <div className="rounded-lg border border-brand-100 bg-brand-50 px-4 py-3 text-sm text-gray-700">
                      <strong>
                        Product:
                      </strong>{" "}
                      {
                        form.product_id
                      }{" "}
                      —{" "}
                      {getProductName(
                        form.product_id
                      )}{" "}
                      (
                      {getProductSku(
                        form.product_id
                      )}
                      )
                      <br />
                      <strong>
                        Standard category:
                      </strong>{" "}
                      {getProductCategory(
                        form.product_id,
                        "—"
                      )}
                    </div>
                  )}

                <div className="rounded-lg bg-gray-50 px-4 py-3 text-sm text-gray-600">
                  <strong>
                    New product stock:
                  </strong>{" "}
                  Starting stock is the initial quantity
                  currently available. The product category
                  comes automatically from the product catalog.
                  This starting stock does not create a movement
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
                  <strong>
                    Product:
                  </strong>{" "}
                  {
                    existingFormRow.product_id
                  }{" "}
                  —{" "}
                  {getProductName(
                    existingFormRow.product_id
                  )}{" "}
                  (
                  {getProductSku(
                    existingFormRow.product_id
                  )}
                  )
                  <br />

                  <strong>
                    Category:
                  </strong>{" "}
                  {getProductCategory(
                    existingFormRow.product_id,
                    existingFormRow.category
                  )}
                  <br />

                  <strong>
                    Current stock:
                  </strong>{" "}
                  {
                    existingFormRow.inventory_level
                  }{" "}
                  units
                </div>

                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <label className="space-y-1 text-sm font-medium text-gray-700">
                    Movement Type

                    <select
                      required
                      value={
                        movementType
                      }
                      onChange={(
                        event
                      ) =>
                        setMovementType(
                          event
                            .target
                            .value as
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
                      value={
                        quantityDelta
                      }
                      onChange={(
                        event
                      ) =>
                        setQuantityDelta(
                          event
                            .target
                            .value
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
                      value={
                        movementReason
                      }
                      onChange={(
                        event
                      ) =>
                        setMovementReason(
                          event
                            .target
                            .value
                        )
                      }
                      placeholder={
                        movementType ===
                        "DELIVERY"
                          ? "e.g. Supplier delivery"
                          : movementType ===
                            "RETURN"
                          ? "e.g. Customer returned items"
                          : "e.g. Damaged stock correction"
                      }
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal"
                    />
                  </label>
                </div>

                <div className="rounded-lg bg-gray-50 px-4 py-3 text-sm text-gray-600">
                  <strong>
                    History:
                  </strong>{" "}
                  This change will be saved with the movement type,
                  reason, quantity before, quantity after, and
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
            onChange={(event) => {
              setSearch(
                event.target.value
              );
              setPage(1);
            }}
            placeholder="Search product, SKU, category, store, region..."
            className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none sm:w-72"
            aria-label="Search inventory rows"
          />

          <select
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none"
            value={category}
            onChange={(event) => {
              setCategory(
                event.target.value
              );
              setPage(1);
            }}
            aria-label="Filter by category"
          >
            <option value="">
              All categories
            </option>

            {CATEGORIES.map(
              (item) => (
                <option
                  key={item}
                  value={item}
                >
                  {item}
                </option>
              )
            )}
          </select>

          <select
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none"
            value={productFilter}
            onChange={(event) =>
              changeProduct(
                event.target.value
              )
            }
            aria-label="Filter by product"
          >
            <option value="">
              All products
            </option>

            {(
              productsData?.products ??
              []
            ).map(
              (product) => (
                <option
                  key={
                    product.product_id
                  }
                  value={
                    product.product_id
                  }
                >
                  {
                    product.product_id
                  }{" "}
                  —{" "}
                  {
                    product.name
                  }
                </option>
              )
            )}
          </select>

          <select
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none"
            value={storeFilter}
            onChange={(event) => {
              setStoreFilter(
                event.target.value
              );
              setPage(1);
            }}
            aria-label="Filter by store"
          >
            <option value="">
              All stores
            </option>

            {storeIds.map(
              (storeId) => (
                <option
                  key={storeId}
                  value={storeId}
                >
                  {storeId}
                </option>
              )
            )}
          </select>

          <select
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none"
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(
                event.target.value as
                  | "all"
                  | "low"
              );
              setPage(1);
            }}
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

        {error && (
          <ErrorState message={error} />
        )}

        {!loading && !error && (
          <>
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    {COLUMNS.map(
                      (column) => (
                        <th
                          key={
                            column.key
                          }
                          className="whitespace-nowrap px-4 py-2.5 text-left"
                        >
                          <button
                            type="button"
                            onClick={() =>
                              toggleSort(
                                column.key
                              )
                            }
                            className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-gray-500 hover:text-gray-800"
                            aria-label={`Sort by ${column.label}`}
                          >
                            {
                              column.label
                            }

                            <span
                              aria-hidden="true"
                              className={
                                sortKey ===
                                column.key
                                  ? "text-brand-600"
                                  : "text-gray-300"
                              }
                            >
                              {sortKey ===
                              column.key
                                ? sortDir ===
                                  "asc"
                                  ? "▲"
                                  : "▼"
                                : "↕"}
                            </span>
                          </button>
                        </th>
                      )
                    )}

                    {[
                      "Status",
                      "Actions",
                    ].map(
                      (
                        heading
                      ) => (
                        <th
                          key={
                            heading
                          }
                          className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500"
                        >
                          {
                            heading
                          }
                        </th>
                      )
                    )}
                  </tr>
                </thead>

                <tbody className="divide-y divide-gray-100">
                  {paged.map(
                    (row) => {
                      const product =
                        productMap.get(
                          row.product_id
                        );

                      const displayCategory =
                        product?.category ??
                        row.category;

                      return (
                        <tr
                          key={`${row.store_id}-${row.product_id}`}
                          className="transition-colors hover:bg-brand-50/50"
                        >
                          <td className="px-4 py-2 font-medium text-gray-900">
                            <div>
                              {product?.name ??
                                row.product_id}
                            </div>

                            <div className="text-xs font-normal text-gray-500">
                              {
                                row.product_id
                              }

                              {product?.sku
                                ? ` · ${product.sku}`
                                : ""}
                            </div>
                          </td>

                          <td className="whitespace-nowrap px-4 py-2 text-gray-600">
                            {
                              displayCategory
                            }
                          </td>

                          <td className="whitespace-nowrap px-4 py-2 text-gray-600">
                            {
                              row.region
                            }
                          </td>

                          <td className="whitespace-nowrap px-4 py-2 text-gray-600">
                            {
                              row.store_id
                            }
                          </td>

                          <td className="whitespace-nowrap px-4 py-2 tabular-nums text-gray-900">
                            {
                              row.inventory_level
                            }
                          </td>

                          <td className="whitespace-nowrap px-4 py-2 tabular-nums text-gray-600">
                            {
                              row.units_ordered
                            }
                          </td>

                          <td className="whitespace-nowrap px-4 py-2">
                            {row.inventory_level <
                            50 ? (
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
                                beginEdit(
                                  row
                                )
                              }
                              className="mr-2 rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
                            >
                              Edit stock
                            </button>

                            <PinButton
                              productId={
                                row.product_id
                              }
                              rowKey={`${row.product_id}-${row.store_id}`}
                              selectedRowKey={
                                selectedFavoriteRows[
                                  row.product_id
                                ] ?? null
                              }
                              onRowSelected={(
                                rowKey
                              ) =>
                                handleFavoriteRowSelected(
                                  row.product_id,
                                  rowKey
                                )
                              }
                            />
                          </td>
                        </tr>
                      );
                    }
                  )}
                </tbody>
              </table>
            </div>

            {sorted.length ===
              0 && (
              <div className="mt-3">
                <EmptyState
                  title="No matching rows."
                  hint="Try widening the filters — e.g. clear the search box, the product filter, or the low-stock-onlyilter."
                />
              </div>
            )}

            {sorted.length >
              PAGE_SIZE && (
              <nav
                className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm"
                aria-label="Inventory pages"
              >
                <span className="text-gray-500">
                  Showing{" "}
                  {(currentPage -
                    1) *
                    PAGE_SIZE +
                    1}
                  –
                  {Math.min(
                    currentPage *
                      PAGE_SIZE,
                    sorted.length
                  )}{" "}
                  of{" "}
                  {
                    sorted.length
                  }{" "}
                  rows
                </span>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      setPage(
                        (
                          current
                        ) =>
                          Math.max(
                            1,
                            current -
                              1
                          )
                      )
                    }
                    disabled={
                      currentPage ===
                      1
                    }
                    className="rounded-lg border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    ← Previous
                  </button>

                  <span className="tabular-nums text-gray-600">
                    Page{" "}
                    {
                      currentPage
                    }{" "}
                    of{" "}
                    {
                      pageCount
                    }
                  </span>

                  <button
                    type="button"
                    onClick={() =>
                      setPage(
                        (
                          current
                        ) =>
                          Math.min(
                            pageCount,
                            current +
                              1
                          )
                      )
                    }
                    disabled={
                      currentPage ===
                      pageCount
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
              {movements?.length ??
                0}{" "}
              movements
            </span>
          </div>
        </div>

        <div className="mb-4 flex flex-wrap gap-2">
          <select
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none"
            value={
              movementTypeFilter
            }
            onChange={(event) =>
              setMovementTypeFilter(
                event.target.value
              )
            }
            aria-label="Filter by movement type"
          >
            <option value="">
              All movement types
            </option>

            {MOVEMENT_TYPES.map(
              (type) => (
                <option
                  key={type}
                  value={type}
                >
                  {
                    movementLabel(
                      type
                    )
                  }
                </option>
              )
            )}
          </select>

          <span className="flex items-center rounded-lg bg-gray-50 px-3 py-1.5 text-xs text-gray-500">
            Product:{" "}
            {productFilter
              ? `${productFilter} — ${getProductName(
                  productFilter
                )}`
              : "All"}
          </span>

          <span className="flex items-center rounded-lg bg-gray-50 px-3 py-1.5 text-xs text-gray-500">
            Store:{" "}
            {
              storeFilter ||
              "All"
            }
          </span>
        </div>

        {movementsLoading && (
          <LoadingState label="Loading stock movement history..." />
        )}

        {movementsError && (
          <ErrorState
            message={
              movementsError
            }
          />
        )}

        {!movementsLoading &&
          !movementsError && (
            <>
              {!movements ||
              movements.length ===
                0 ? (
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
                        (
                          movement
                        ) => {
                          const product =
                            productMap.get(
                              movement.product_id
                            );

                          return (
                            <tr
                              key={
                                movement.id
                              }
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

                              <td className="px-4 py-3 font-medium text-gray-900">
                                <div>
                                  {product?.name ??
                                    movement.product_id}
                                </div>

                                <div className="text-xs font-normal text-gray-500">
                                  {
                                    movement.product_id
                                  }

                                  {product?.sku
                                    ? ` · ${product.sku}`
                                    : ""}
                                </div>
                              </td>

                              <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                                {
                                  movement.store_id
                                }
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
                                {
                                  movement.reason
                                }
                              </td>
                            </tr>
                          );
                        }
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