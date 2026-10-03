// frontend/src/pages/Watchlist.tsx
//
// Pinned products. Every figure here is recomputed by the server on each load
// (same stockout/reorder services the dedicated pages use), so a pin can never
// show a number that has drifted from the analytical tables.

import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, getWatchlist, setWatchlistNote, unpinProduct } from "../services/api";
import { useApi } from "../hooks/useApi";
import { useWatchlist } from "../hooks/useWatchlist";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import RiskBadge from "../components/RiskBadge";
import StatCard from "../components/StatCard";
import { LoadingState, ErrorState } from "../components/LoadingError";

function NoteEditor({ productId, initial }: { productId: string; initial: string | null }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(initial ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    try {
      await setWatchlistNote(productId, text.trim() || null);
      setEditing(false);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save that note.");
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => {
          setText(initial ?? "");
          setEditing(true);
        }}
        className="text-left text-sm text-gray-600 hover:text-gray-900"
      >
        {initial ? (
          <span className="italic">“{initial}”</span>
        ) : (
          <span className="text-gray-400 underline decoration-dotted">+ add a note</span>
        )}
      </button>
    );
  }

  return (
    <div className="space-y-1">
      <input
        autoFocus
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") void save();
          if (e.key === "Escape") setEditing(false);
        }}
        placeholder="Why is this product pinned?"
        className="w-full rounded-lg border border-gray-300 px-2 py-1 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        aria-label={`Note for ${productId}`}
      />
      <div className="flex gap-2">
        <button
          type="button"
          disabled={saving}
          onClick={() => void save()}
          className="rounded-lg bg-brand-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save"}
        </button>
        <button
          type="button"
          onClick={() => setEditing(false)}
          className="rounded-lg border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50"
        >
          Cancel
        </button>
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}

export default function Watchlist() {
  const { data, loading, error } = useApi(() => getWatchlist(), []);
  const { refresh } = useWatchlist();
  const [unpinError, setUnpinError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);

  const entries = data?.entries ?? [];
  const atRisk = entries.filter((e) => e.risk === "HIGH" || e.risk === "MEDIUM").length;
  const totalOrder = entries.reduce((sum, e) => sum + (e.recommended_reorder_quantity ?? 0), 0);

  async function handleUnpin(productId: string) {
    setRemoving(productId);
    setUnpinError(null);
    try {
      await unpinProduct(productId);
      await refresh();
    } catch (err) {
      setUnpinError(err instanceof ApiError ? err.message : "Could not unpin that product.");
    } finally {
      setRemoving(null);
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Watchlist"
        subtitle={
          data
            ? `${data.count} product${data.count === 1 ? "" : "s"} pinned. Figures are recomputed on every load, so nothing here goes stale.`
            : "Pin the products you care about and keep their live risk in one place."
        }
        actions={
          <Link
            to="/stockout"
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50"
          >
            Browse stockout risk
          </Link>
        }
      />

      {loading && <LoadingState label="Loading your watchlist..." />}
      {error && <ErrorState message={error} />}
      {unpinError && <ErrorState message={unpinError} />}

      {!loading && !error && entries.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard label="Pinned products" value={entries.length} />
          <StatCard
            label="Needing attention"
            value={atRisk}
            hint="medium or high risk"
            accent={atRisk > 0 ? "warning" : "success"}
          />
          <StatCard
            label="Suggested order"
            value={totalOrder.toFixed(0)}
            hint="units across pinned products"
            accent="info"
          />
        </div>
      )}


      {!loading && !error && entries.length === 0 && (
        <Card>
          <EmptyState
            title="Nothing pinned yet."
            hint="Use the star on any product to keep it here. Start with the stockout risk page — anything at medium or high risk is usually worth pinning."
            action={
              <Link
                to="/stockout"
                className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
              >
                Go to Stockout Risk
              </Link>
            }
          />
        </Card>
      )}

      {!loading && !error && entries.length > 0 && (
        <div className="space-y-3">
          {entries.map((entry) => (
            <Card key={entry.product_id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-gray-900">{entry.product_id}</span>
                    {entry.risk ? (
                      <RiskBadge risk={entry.risk} />
                    ) : (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                        not scored
                      </span>
                    )}
                  </div>


                  <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
                    <div>
                      <dt className="text-xs uppercase tracking-wide text-gray-400">On hand</dt>
                      <dd className="tabular-nums font-medium text-gray-800">
                        {entry.current_inventory === null ? "—" : entry.current_inventory.toFixed(0)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase tracking-wide text-gray-400">Order qty</dt>
                      <dd className="tabular-nums font-medium text-gray-800">
                        {entry.recommended_reorder_quantity === null
                          ? "—"
                          : entry.recommended_reorder_quantity.toFixed(0)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase tracking-wide text-gray-400">Lead time</dt>
                      <dd className="tabular-nums font-medium text-gray-800">
                        {entry.lead_time_days === null ? "—" : `${entry.lead_time_days}d`}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase tracking-wide text-gray-400">Pinned</dt>
                      <dd className="font-medium text-gray-800">
                        {new Date(entry.pinned_at).toLocaleDateString()}
                      </dd>
                    </div>
                  </dl>

                  {entry.reason && <p className="mt-2 text-xs text-gray-500">{entry.reason}</p>}

                  <div className="mt-3 border-t border-gray-100 pt-2">
                    <NoteEditor productId={entry.product_id} initial={entry.note} />
                  </div>
                </div>

                <div className="flex shrink-0 flex-col items-end gap-2">
                  <div className="flex gap-2 text-xs font-medium">
                    <Link to={`/forecast?product=${entry.product_id}`} className="text-brand-700 hover:underline">
                      Forecast →
                    </Link>
                    <Link to={`/stockout?product=${entry.product_id}`} className="text-brand-700 hover:underline">
                      Risk →
                    </Link>
                    <Link to={`/inventory?product=${entry.product_id}`} className="text-brand-700 hover:underline">
                      Stock →
                    </Link>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleUnpin(entry.product_id)}
                    disabled={removing === entry.product_id}
                    className="rounded-lg border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 hover:text-red-600 disabled:opacity-50"
                  >
                    {removing === entry.product_id ? "Removing..." : "Unpin"}
                  </button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

