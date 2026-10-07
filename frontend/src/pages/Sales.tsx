// frontend/src/pages/Sales.tsx

import { ChangeEvent, FormEvent, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, BarChart, Bar } from "recharts";
import {
  ApiError,
  bulkImportSales,
  closeSalesDay,
  getCurrentInventory,
  getProductCosts,
  getSales,
  getSalesDayCoverage,
  getSalesByCategory,
  getSalesByStore,
  getSalesSourcesSummary,
  getSalesTrend,
  getStoreProfitability,
  getTopProducts,
  recordSale,
} from "../services/api";
import type { BulkImportResponse } from "../types/sales";
import { useApi } from "../hooks/useApi";
import { LoadingState, ErrorState } from "../components/LoadingError";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import StatCard from "../components/StatCard";
import { downloadCsv } from "../lib/csv";

type SourceFilterType = "all" | "genuine" | "Real · Manual" | "Real · CSV Import" | "Sample Data";

export default function Sales() {
  const [activeTab, setActiveTab] = useState<"record" | "import">("record");
  const [sourceFilter, setSourceFilter] = useState<SourceFilterType>("all");
  const [granularity, setGranularity] = useState<"daily" | "weekly" | "monthly">("monthly");
  const [refreshKey, setRefreshKey] = useState(0);

  // Manual Sale Form state
  const [selectedStockKey, setSelectedStockKey] = useState("");
  const [unitsSold, setUnitsSold] = useState("1");
  const [unitPrice, setUnitPrice] = useState("");
  const [unitCost, setUnitCost] = useState("");
  const [saleCategory, setSaleCategory] = useState("Groceries");
  const [saleRegion, setSaleRegion] = useState("East");
  const [savingSale, setSavingSale] = useState(false);
  const [saleError, setSaleError] = useState("");
  const [saleSuccess, setSaleSuccess] = useState("");
  const [closingDate, setClosingDate] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  });
  const [closingStore, setClosingStore] = useState("");
  const [closingDay, setClosingDay] = useState(false);
  const [closeDayMessage, setCloseDayMessage] = useState("");
  const [closeDayError, setCloseDayError] = useState("");

  // CSV Bulk Import state
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvTextPreview, setCsvTextPreview] = useState("");
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState("");
  const [importResult, setImportResult] = useState<BulkImportResponse | null>(null);

  // Sales Records Table filter state
  const [tableProductFilter, setTableProductFilter] = useState("");
  const [tableStoreFilter, setTableStoreFilter] = useState("");

  // Calculate API filter params from sourceFilter
  const apiFilterParams = useMemo(() => {
    if (sourceFilter === "genuine") return { genuine_only: true, source: undefined };
    if (sourceFilter === "all") return { genuine_only: false, source: undefined };
    return { genuine_only: false, source: sourceFilter };
  }, [sourceFilter]);

  // Queries
  const stock = useApi(() => getCurrentInventory(), [refreshKey]);
  const productCosts = useApi(() => getProductCosts(), [refreshKey]);
  const profitability = useApi(() => getStoreProfitability(), [refreshKey]);
  const sourcesSummary = useApi(() => getSalesSourcesSummary(), [refreshKey]);
  const dayCoverage = useApi(() => getSalesDayCoverage(), [refreshKey]);
  const top = useApi(
    () => getTopProducts(10, undefined, undefined, apiFilterParams.source, apiFilterParams.genuine_only),
    [apiFilterParams, refreshKey]
  );
  const byCategory = useApi(
    () => getSalesByCategory(apiFilterParams),
    [apiFilterParams, refreshKey]
  );
  const byStore = useApi(
    () => getSalesByStore(apiFilterParams),
    [apiFilterParams, refreshKey]
  );
  const trend = useApi(
    () => getSalesTrend({ granularity, ...apiFilterParams }),
    [granularity, apiFilterParams, refreshKey]
  );
  const salesList = useApi(
    () =>
      getSales({
        ...apiFilterParams,
        product_id: tableProductFilter || undefined,
        store_id: tableStoreFilter || undefined,
        limit: 50,
      }),
    [apiFilterParams, tableProductFilter, tableStoreFilter, refreshKey]
  );

  const stockRows = stock.data ?? [];
  const storeIds = [...new Set(stockRows.map((row) => row.store_id))].sort();
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
      const knownCost = productCosts.data?.products.find((item) => item.product_id === row.product_id)?.cost_price;
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
        unit_cost: unitCost.trim() ? Number(unitCost) : undefined,
        category: saleCategory,
        region: saleRegion,
      });
      setSaleSuccess(`Sale recorded and tagged as "${result.source}". ${result.remaining_inventory} units remain for ${result.product_id} at ${result.store_id}. ${result.gross_profit == null ? "No cost was saved for this sale, so it is excluded from profit reporting." : `Estimated gross profit/loss: $${result.gross_profit.toFixed(2)}.`}`);
      setRefreshKey((key) => key + 1);
    } catch (err) {
      setSaleError(err instanceof ApiError ? err.message : "Could not record the sale. Please try again.");
    } finally {
      setSavingSale(false);
    }
  }

  async function submitCloseDay(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!closingStore) return;
    setClosingDay(true);
    setCloseDayError("");
    setCloseDayMessage("");
    try {
      const result = await closeSalesDay({ business_date: closingDate, store_id: closingStore });
      setCloseDayMessage(
        result.already_closed
          ? `Sales for ${result.store_id} on ${result.business_date} were already marked complete.`
          : `Sales for ${result.store_id} on ${result.business_date} are marked complete, including a zero-sales day if nothing was sold.`
      );
      setRefreshKey((key) => key + 1);
    } catch (err) {
      setCloseDayError(err instanceof ApiError ? err.message : "Could not mark this sales day complete.");
    } finally {
      setClosingDay(false);
    }
  }

  async function handleFileSelected(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setCsvFile(file);
    setImportError("");
    setImportResult(null);
    try {
      const text = await file.text();
      setCsvTextPreview(text);
    } catch {
      setImportError("Could not read the selected CSV file.");
    }
  }

  async function submitBulkImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!csvTextPreview.trim()) {
      setImportError("Please select a CSV file or enter CSV data.");
      return;
    }
    setImporting(true);
    setImportError("");
    setImportResult(null);
    try {
      const res = await bulkImportSales({ csv_content: csvTextPreview });
      setImportResult(res);
      if (res.imported_count > 0) {
        setRefreshKey((key) => key + 1);
      }
    } catch (err) {
      setImportError(err instanceof ApiError ? err.message : "Bulk import failed. Please verify file format.");
    } finally {
      setImporting(false);
    }
  }

  function downloadTemplate() {
    const templateContent = [
      "date,store_id,product_id,units_sold,price,category,region,discount,holiday_promotion",
      "2025-01-15,S001,P0001,12,49.99,Electronics,East,0,0",
      "2025-01-16,S002,P0002,5,19.99,Toys,North,10,1",
      "2025-01-17,S003,P0003,8,34.50,Furniture,West,0,0",
    ].join("\r\n");
    downloadCsv("sales_import_template.csv", templateContent);
  }

  const anyLoading = [top, byCategory, byStore, trend].some((q) => q.loading);
  const firstError = [top, byCategory, byStore, trend].find((q) => q.error)?.error;

  if (anyLoading && !top.data && !trend.data) return <LoadingState label="Loading sales analytics..." />;
  if (firstError && !top.data && !trend.data) return <ErrorState message={firstError} />;

  const summary = sourcesSummary.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Sales Analytics & Operations"
        subtitle="Manage genuine sales, perform bulk CSV imports, and analyze genuine demand separately from the synthetic sample dataset."
      />

      <Card>
        <h2 className="text-lg font-semibold text-gray-900">Confirm a complete sales day</h2>
        <p className="mt-1 text-sm text-gray-600">
          After all sales for a store and date are entered, mark the day complete. This confirms that a missing sale means zero sales, which is important for future real-data forecasts.
        </p>
        <form onSubmit={submitCloseDay} className="mt-4 flex flex-wrap items-end gap-3">
          <label className="space-y-1 text-sm font-medium text-gray-700">
            Store
            <select required value={closingStore} onChange={(event) => setClosingStore(event.target.value)} className="block rounded-lg border border-gray-300 bg-white px-3 py-2 font-normal">
              <option value="">Select store</option>
              {storeIds.map((storeId) => <option key={storeId} value={storeId}>{storeId}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-sm font-medium text-gray-700">
            Business date
            <input required type="date" value={closingDate} onChange={(event) => setClosingDate(event.target.value)} className="block rounded-lg border border-gray-300 px-3 py-2 font-normal" />
          </label>
          <button type="submit" disabled={closingDay || stock.loading || !closingStore} className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50">
            {closingDay ? "Saving…" : "Mark sales day complete"}
          </button>
        </form>
        {closeDayError && <p role="alert" className="mt-3 text-sm text-red-700">{closeDayError}</p>}
        {closeDayMessage && <p role="status" className="mt-3 text-sm text-green-700">{closeDayMessage}</p>}
        {dayCoverage.data && (
          <div className="mt-4 rounded-lg bg-gray-50 p-3 text-sm text-gray-700">
            {(() => {
              const selectedCoverage = dayCoverage.data.stores.find((item) => item.store_id === closingStore);
              const count = selectedCoverage?.complete_days_last_365 ?? 0;
              return <>{closingStore || "Selected store"}: <strong>{count} / 180</strong> complete days in the last year for an initial real-data model evaluation. About 365 days helps evaluate annual seasonality. Meeting these counts does not guarantee the real model will outperform the current forecast.</>;
            })()}
          </div>
        )}
      </Card>

      {/* KPI Overview Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Genuine Real Sales"
          value={summary ? summary.genuine_sales_count.toLocaleString() : "..."}
          hint="Real · Manual + Real · CSV Import"
          accent="success"
        />
        <StatCard
          label="Real · Manual"
          value={summary ? summary.real_manual_count.toLocaleString() : "..."}
          hint="Sales entered manually"
          accent="info"
        />
        <StatCard
          label="Real · CSV Import"
          value={summary ? summary.real_csv_import_count.toLocaleString() : "..."}
          hint="Bulk imported via CSV"
          accent="info"
        />
        <StatCard
          label="Sample Dataset"
          value={summary ? summary.sample_data_count.toLocaleString() : "..."}
          hint="Synthetic baseline (2022–2024)"
          accent="default"
        />
      </div>

      {/* Operation Tabs: Manual Entry or Bulk CSV Import */}
      <Card>
        <div className="border-b border-gray-200 pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setActiveTab("record")}
                className={`rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
                  activeTab === "record"
                    ? "bg-brand-600 text-white shadow-sm"
                    : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                }`}
              >
                ➕ Record Sale (Real · Manual)
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("import")}
                className={`rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
                  activeTab === "import"
                    ? "bg-purple-600 text-white shadow-sm"
                    : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                }`}
              >
                📤 Bulk CSV Import (Real · CSV Import)
              </button>
            </div>
            <span className="text-xs text-gray-500">
              Labels are stored directly in the database to separate genuine transactions from sample data.
            </span>
          </div>
        </div>

        {activeTab === "record" ? (
          <form onSubmit={submitSale} className="mt-4 space-y-4">
            <div className="rounded-lg bg-blue-50/70 p-3 text-xs text-blue-800 border border-blue-200 flex items-center justify-between">
              <span>
                Sales recorded through this form are permanently labeled as <strong>Real · Manual</strong> in the database and deducted from current inventory.
              </span>
              <span className="rounded bg-blue-200 px-2 py-0.5 font-semibold text-blue-900 text-[11px]">Real · Manual</span>
            </div>

            {stock.error && <p role="alert" className="text-sm text-red-700">{stock.error}</p>}
            {stockRows.length === 0 && !stock.loading && !stock.error && (
              <p className="text-sm text-gray-600">Add product stock on the Inventory page before recording a sale.</p>
            )}

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <label className="space-y-1 text-sm font-medium text-gray-700">
                Product at store
                <select
                  required
                  value={selectedStockKey}
                  onChange={(event) => selectStock(event.target.value)}
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-normal text-sm"
                >
                  <option value="" disabled>
                    {stock.loading ? "Loading stock…" : "Select product and store"}
                  </option>
                  {stockRows.map((row) => (
                    <option key={`${row.product_id}::${row.store_id}`} value={`${row.product_id}::${row.store_id}`}>
                      {row.product_id} · {row.store_id} · {row.inventory_level} on hand
                    </option>
                  ))}
                </select>
              </label>

              <label className="space-y-1 text-sm font-medium text-gray-700">
                Quantity sold
                <input
                  required
                  type="number"
                  min="1"
                  max={selectedStock?.inventory_level}
                  step="1"
                  value={unitsSold}
                  onChange={(event) => setUnitsSold(event.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal text-sm"
                />
              </label>

              <label className="space-y-1 text-sm font-medium text-gray-700">
                Unit price ($)
                <input
                  required
                  type="number"
                  min="0"
                  step="0.01"
                  value={unitPrice}
                  onChange={(event) => setUnitPrice(event.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal text-sm"
                />
              </label>

              <label className="space-y-1 text-sm font-medium text-gray-700">
                Unit cost ($)
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={unitCost}
                  onChange={(event) => setUnitCost(event.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal text-sm"
                />
              </label>

              <label className="space-y-1 text-sm font-medium text-gray-700">
                Category
                <select
                  required
                  value={saleCategory}
                  onChange={(event) => setSaleCategory(event.target.value)}
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-normal text-sm"
                >
                  {["Furniture", "Toys", "Clothing", "Groceries", "Electronics"].map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </label>

              <label className="space-y-1 text-sm font-medium text-gray-700">
                Region
                <select
                  required
                  value={saleRegion}
                  onChange={(event) => setSaleRegion(event.target.value)}
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-normal text-sm"
                >
                  {["North", "South", "East", "West"].map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </label>
            </div>

            <p className="text-xs text-gray-500">
              Unit cost is prefilled from the product catalog when available. Each sale keeps its own cost snapshot for profit reports.
            </p>

            {saleError && <p role="alert" className="text-sm font-medium text-red-700">{saleError}</p>}
            {saleSuccess && <p role="status" className="text-sm font-medium text-green-700">{saleSuccess}</p>}

            <div className="flex items-center justify-between pt-1">
              <button
                disabled={savingSale || stock.loading || !selectedStock}
                type="submit"
                className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {savingSale ? "Recording sale…" : "Record Real · Manual Sale"}
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={submitBulkImport} className="mt-4 space-y-4">
            <div className="rounded-lg bg-purple-50/70 p-3 text-xs text-purple-900 border border-purple-200 flex flex-wrap items-center justify-between gap-2">
              <span>
                Sales imported from CSV are marked as <strong>Real · CSV Import</strong> in the database. Duplicate records (within the file or already in database) and invalid rows are detected and reported.
              </span>
              <div className="flex items-center gap-2">
                <span className="rounded bg-purple-200 px-2 py-0.5 font-semibold text-purple-900 text-[11px]">Real · CSV Import</span>
                <button
                  type="button"
                  onClick={downloadTemplate}
                  className="rounded border border-purple-300 bg-white px-2.5 py-1 text-xs font-medium text-purple-700 hover:bg-purple-50 shadow-sm"
                >
                  📥 Download CSV Template
                </button>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700">
                  Select CSV File
                  <input
                    type="file"
                    accept=".csv,text/csv"
                    onChange={handleFileSelected}
                    className="mt-1 block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-purple-50 file:px-3 file:py-1 file:text-xs file:font-semibold file:text-purple-700 hover:file:bg-purple-100"
                  />
                </label>
                {csvFile && (
                  <p className="text-xs text-gray-500">
                    Selected: <strong>{csvFile.name}</strong> ({(csvFile.size / 1024).toFixed(1)} KB)
                  </p>
                )}
                <p className="text-xs text-gray-500">
                  Expected columns: <code className="font-mono text-purple-700">date, store_id, product_id, units_sold, price, category, region</code>
                </p>
              </div>

              <div className="space-y-1">
                <label className="block text-sm font-medium text-gray-700">
                  CSV Content / Raw Text Preview
                  <textarea
                    rows={4}
                    value={csvTextPreview}
                    onChange={(e) => setCsvTextPreview(e.target.value)}
                    placeholder="date,store_id,product_id,units_sold,price,category,region&#10;2025-01-15,S001,P0001,10,49.99,Electronics,East"
                    className="mt-1 w-full rounded-lg border border-gray-300 font-mono text-xs p-2.5 focus:border-purple-500 focus:outline-none"
                  />
                </label>
              </div>
            </div>

            {importError && <p role="alert" className="text-sm font-medium text-red-700">{importError}</p>}

            {/* Import Results Box */}
            {importResult && (
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 pb-2">
                  <h4 className="text-sm font-semibold text-gray-900">Import Summary</h4>
                  <div className="flex gap-2 text-xs">
                    <span className="rounded-md bg-gray-200 px-2 py-0.5 text-gray-700">
                      Total: {importResult.total_rows}
                    </span>
                    <span className="rounded-md bg-emerald-100 px-2 py-0.5 font-semibold text-emerald-800">
                      Imported: {importResult.imported_count}
                    </span>
                    {importResult.duplicates_count > 0 && (
                      <span className="rounded-md bg-amber-100 px-2 py-0.5 font-semibold text-amber-800">
                        Duplicates: {importResult.duplicates_count}
                      </span>
                    )}
                    {importResult.invalid_count > 0 && (
                      <span className="rounded-md bg-red-100 px-2 py-0.5 font-semibold text-red-800">
                        Invalid: {importResult.invalid_count}
                      </span>
                    )}
                  </div>
                </div>

                {importResult.imported_count > 0 && (
                  <p className="text-sm text-emerald-700 font-medium">
                    ✓ Successfully saved {importResult.imported_count} genuine sales records marked as <strong>Real · CSV Import</strong>.
                  </p>
                )}

                {importResult.errors.length > 0 && (
                  <div className="space-y-2">
                    <h5 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                      Detected Issues ({importResult.errors.length})
                    </h5>
                    <div className="max-h-48 overflow-y-auto rounded-lg border border-gray-200 bg-white">
                      <table className="min-w-full divide-y divide-gray-200 text-xs">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-3 py-2 text-left font-medium text-gray-500">Row</th>
                            <th className="px-3 py-2 text-left font-medium text-gray-500">Type</th>
                            <th className="px-3 py-2 text-left font-medium text-gray-500">Key / Identifier</th>
                            <th className="px-3 py-2 text-left font-medium text-gray-500">Error Details</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {importResult.errors.map((err, i) => (
                            <tr key={i} className={err.error_type === "duplicate" ? "bg-amber-50/50" : "bg-red-50/50"}>
                              <td className="px-3 py-1.5 font-mono font-medium text-gray-700">#{err.row}</td>
                              <td className="px-3 py-1.5">
                                <span
                                  className={`rounded px-1.5 py-0.5 font-semibold text-[10px] ${
                                    err.error_type === "duplicate"
                                      ? "bg-amber-200 text-amber-900"
                                      : "bg-red-200 text-red-900"
                                  }`}
                                >
                                  {err.error_type === "duplicate" ? "Duplicate" : "Invalid Row"}
                                </span>
                              </td>
                              <td className="px-3 py-1.5 font-mono text-gray-600">{err.key || "—"}</td>
                              <td className="px-3 py-1.5 text-gray-800">{err.reason}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center justify-between pt-1">
              <button
                disabled={importing || !csvTextPreview.trim()}
                type="submit"
                className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-semibold text-white hover:bg-purple-700 disabled:opacity-50 shadow-sm"
              >
                {importing ? "Validating & importing…" : "Validate and Import CSV"}
              </button>
            </div>
          </form>
        )}
      </Card>

      {/* Filter Toolbar: Genuine vs Sample Data Separation */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-900">Data Source Filter</h3>
            <p className="text-xs text-gray-500">Filter trends, rankings, and records by genuine transactions or sample data</p>
          </div>

          {/* Filter Pills */}
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => setSourceFilter("all")}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                sourceFilter === "all"
                  ? "bg-gray-900 text-white shadow-sm"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              All Sales
            </button>
            <button
              type="button"
              onClick={() => setSourceFilter("genuine")}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                sourceFilter === "genuine"
                  ? "bg-emerald-600 text-white shadow-sm"
                  : "bg-emerald-50 text-emerald-800 hover:bg-emerald-100 border border-emerald-200"
              }`}
            >
              ✨ Genuine Sales Only
            </button>
            <button
              type="button"
              onClick={() => setSourceFilter("Real · Manual")}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                sourceFilter === "Real · Manual"
                  ? "bg-blue-600 text-white shadow-sm"
                  : "bg-blue-50 text-blue-800 hover:bg-blue-100 border border-blue-200"
              }`}
            >
              Real · Manual
            </button>
            <button
              type="button"
              onClick={() => setSourceFilter("Real · CSV Import")}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                sourceFilter === "Real · CSV Import"
                  ? "bg-purple-600 text-white shadow-sm"
                  : "bg-purple-50 text-purple-800 hover:bg-purple-100 border border-purple-200"
              }`}
            >
              Real · CSV Import
            </button>
            <button
              type="button"
              onClick={() => setSourceFilter("Sample Data")}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                sourceFilter === "Sample Data"
                  ? "bg-slate-700 text-white shadow-sm"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              Sample Data (Synthetic)
            </button>
          </div>
        </div>

        {/* Source state banner indicator */}
        {sourceFilter === "genuine" && (
          <div className="rounded-lg bg-emerald-50 p-2.5 text-xs text-emerald-800 border border-emerald-200 flex items-center justify-between">
            <span>
              <strong>Filtered:</strong> Displaying <strong>genuine real sales only</strong> (combining Real · Manual and Real · CSV Import). Synthetic sample dataset records through 2024 are hidden.
            </span>
            <button
              type="button"
              onClick={() => setSourceFilter("all")}
              className="font-medium underline hover:text-emerald-950"
            >
              Reset to all
            </button>
          </div>
        )}
        {sourceFilter === "Sample Data" && (
          <div className="rounded-lg bg-slate-50 p-2.5 text-xs text-slate-700 border border-slate-200 flex items-center justify-between">
            <span>
              <strong>Filtered:</strong> Displaying the <strong>synthetic sample dataset (2022–2024)</strong>. Genuine sales are hidden.
            </span>
            <button
              type="button"
              onClick={() => setSourceFilter("all")}
              className="font-medium underline hover:text-slate-900"
            >
              Reset to all
            </button>
          </div>
        )}
      </div>

      {/* Sales Trend Chart */}
      <Card
        title="Sales Trend"
        subtitle={`${granularity} granularity · ${
          sourceFilter === "all"
            ? "All data"
            : sourceFilter === "genuine"
            ? "Genuine sales only"
            : sourceFilter
        }`}
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
            <Line
              type="monotone"
              dataKey="total_units_sold"
              stroke={sourceFilter === "genuine" ? "#059669" : "#2563eb"}
              dot={false}
              strokeWidth={2.5}
            />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      {/* Analytics Breakdown Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Top-Selling Products" subtitle="Top 10 by units sold">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={top.data?.products ?? []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis type="number" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="product_id" fontSize={11} width={50} tickLine={false} axisLine={false} />
              <Tooltip formatter={(v) => [`${Number(v).toLocaleString()} units`, "Sold"]} cursor={{ fill: "#eff6ff" }} />
              <Bar
                dataKey="total_units_sold"
                fill={sourceFilter === "genuine" ? "#059669" : "#2563eb"}
                radius={[0, 6, 6, 0]}
              />
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

      <Card title="Store Profit and Loss" subtitle="Gross profit on recorded sales with saved unit costs. Historical sample sales without costs are excluded.">
        {profitability.loading ? (
          <p className="text-sm text-gray-500">Calculating store results…</p>
        ) : profitability.error ? (
          <ErrorState message={profitability.error} />
        ) : (profitability.data?.items.length ?? 0) === 0 ? (
          <p className="text-sm text-gray-600">Record sales with unit costs to see store gross profit or loss.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b text-xs uppercase text-gray-500">
                <tr><th className="px-3 py-2">Store</th><th className="px-3 py-2">Net revenue (costed)</th><th className="px-3 py-2">Cost of goods</th><th className="px-3 py-2">Gross profit/loss</th><th className="px-3 py-2">Cost coverage</th><th className="px-3 py-2">Condition</th></tr>
              </thead>
              <tbody className="divide-y">
                {profitability.data?.items.map((item) => (
                  <tr key={item.store_id}>
                    <td className="px-3 py-2 font-medium">{item.store_id}</td>
                    <td className="px-3 py-2">${item.costed_net_revenue.toFixed(2)}</td>
                    <td className="px-3 py-2">${item.known_cost_of_goods_sold.toFixed(2)}</td>
                    <td className={`px-3 py-2 font-semibold ${item.condition === "loss" ? "text-red-700" : item.condition === "profit" ? "text-green-700" : "text-gray-600"}`}>
                      {item.gross_profit_or_loss == null ? "Unknown" : `$${item.gross_profit_or_loss.toFixed(2)}`}
                    </td>
                    <td className="px-3 py-2">{item.cost_coverage_percent.toFixed(0)}%</td>
                    <td className="px-3 py-2 capitalize">{item.condition.replace("_", " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-3 text-xs text-gray-500">{profitability.data?.cost_note}</p>
      </Card>

      {/* Detailed Sales Records Table */}
      <Card
        title="Sales Records"
        subtitle={`Displaying records (${salesList.data?.length ?? 0} shown) · Source: ${
          sourceFilter === "all" ? "All" : sourceFilter === "genuine" ? "Genuine Sales" : sourceFilter
        }`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              placeholder="Search product (e.g. P0001)..."
              value={tableProductFilter}
              onChange={(e) => setTableProductFilter(e.target.value.trim())}
              className="rounded-lg border border-gray-300 px-2.5 py-1 text-xs shadow-sm focus:border-brand-500 focus:outline-none"
            />
            <select
              value={tableStoreFilter}
              onChange={(e) => setTableStoreFilter(e.target.value)}
              className="rounded-lg border border-gray-300 bg-white px-2.5 py-1 text-xs shadow-sm focus:border-brand-500 focus:outline-none"
            >
              <option value="">All stores</option>
              {["S001", "S002", "S003", "S004", "S005"].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
        }
      >
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 text-xs">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Date</th>
                <th className="px-3 py-2 text-left font-medium">Data Provenance</th>
                <th className="px-3 py-2 text-left font-medium">Product</th>
                <th className="px-3 py-2 text-left font-medium">Store</th>
                <th className="px-3 py-2 text-left font-medium">Category</th>
                <th className="px-3 py-2 text-left font-medium">Region</th>
                <th className="px-3 py-2 text-right font-medium">Units Sold</th>
                <th className="px-3 py-2 text-right font-medium">Price</th>
                <th className="px-3 py-2 text-right font-medium">Total Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {(salesList.data ?? []).length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-3 py-8 text-center text-gray-500">
                    No sales records found matching the current filters.
                  </td>
                </tr>
              ) : (
                (salesList.data ?? []).map((row, idx) => {
                  const isManual = row.source === "Real · Manual";
                  const isCsv = row.source === "Real · CSV Import";
                  return (
                    <tr key={`${row.date}-${row.store_id}-${row.product_id}-${idx}`} className="hover:bg-gray-50">
                      <td className="px-3 py-2 font-mono text-gray-900">{row.date}</td>
                      <td className="px-3 py-2">
                        {isManual ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 font-semibold text-emerald-800 border border-emerald-300">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-600"></span>
                            Real · Manual
                          </span>
                        ) : isCsv ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-purple-100 px-2 py-0.5 font-semibold text-purple-800 border border-purple-300">
                            <span className="h-1.5 w-1.5 rounded-full bg-purple-600"></span>
                            Real · CSV Import
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 font-medium text-gray-600 border border-gray-300">
                            <span className="h-1.5 w-1.5 rounded-full bg-gray-400"></span>
                            Sample Data
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono font-medium text-gray-900">{row.product_id}</td>
                      <td className="px-3 py-2 font-mono text-gray-700">{row.store_id}</td>
                      <td className="px-3 py-2 text-gray-700">{row.category}</td>
                      <td className="px-3 py-2 text-gray-700">{row.region}</td>
                      <td className="px-3 py-2 text-right font-semibold text-gray-900">{row.units_sold}</td>
                      <td className="px-3 py-2 text-right text-gray-700">${row.price.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right font-medium text-gray-900">
                        ${(row.units_sold * row.price).toFixed(2)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
