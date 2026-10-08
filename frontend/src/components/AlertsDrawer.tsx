// frontend/src/components/AlertsDrawer.tsx
//
// Notification drawer for proactive stockout alerts.
// Uses the durable REST alerts endpoint so alerts remain available
// even without the removed Live Operations page.

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import {
  acknowledgeAlert,
  getLiveAlerts,
} from "../services/api";

export function AlertsBell() {
  const [open, setOpen] = useState(false);

  const { data } = useApi(
    () => getLiveAlerts(false, 50),
    [open]
  );

  const count = data?.count ?? 0;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="relative shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900"
        aria-label={`Open alerts (${count} open)`}
        title="Stockout alerts"
      >
        🔔 Alerts

        {count > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-600 px-1 text-[11px] font-bold text-white">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>

      {open && (
        <AlertsDrawer
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

export default function AlertsDrawer({
  onClose,
}: {
  onClose: () => void;
}) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState("");

  const { data, loading, error } = useApi(
    () => getLiveAlerts(false, 50),
    [refreshKey]
  );

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener(
      "keydown",
      handleKeyDown
    );

    return () => {
      window.removeEventListener(
        "keydown",
        handleKeyDown
      );
    };
  }, [onClose]);

  async function handleAcknowledge(id: number) {
    setBusyId(id);
    setActionError("");

    try {
      await acknowledgeAlert(id);
      setRefreshKey((value) => value + 1);
    } catch {
      setActionError(
        `Could not acknowledge alert #${id}. Try again.`
      );
    } finally {
      setBusyId(null);
    }
  }

  const alerts = data?.alerts ?? [];

  return (
    <div
      className="fixed inset-0 z-[100]"
      role="dialog"
      aria-modal="true"
      aria-label="Stockout alerts"
    >
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Close alerts"
        onClick={onClose}
        className="absolute inset-0 h-full w-full cursor-default bg-black/30"
      />

      {/* Drawer */}
      <section className="absolute right-0 top-0 flex h-screen w-full max-w-md flex-col bg-white shadow-2xl">
        {/* Header */}
        <header className="flex shrink-0 items-center justify-between border-b border-gray-200 bg-white px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              Alerts
            </h2>

            <p className="mt-0.5 text-sm text-gray-500">
              {alerts.length} open stockout alert
              {alerts.length === 1 ? "" : "s"}
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-50"
          >
            Close ✕
          </button>
        </header>

        {/* Alert content */}
        <div className="min-h-0 flex-1 overflow-y-auto bg-gray-50 px-4 py-4">
          {loading && (
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <p className="text-sm text-gray-500">
                Loading alerts…
              </p>
            </div>
          )}

          {error && (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 p-4"
            >
              <p className="text-sm text-red-700">
                {error}
              </p>
            </div>
          )}

          {actionError && (
            <div
              role="alert"
              className="mb-3 rounded-lg border border-red-200 bg-red-50 p-3"
            >
              <p className="text-sm text-red-700">
                {actionError}
              </p>
            </div>
          )}

          {!loading &&
            !error &&
            alerts.length === 0 && (
              <div className="rounded-lg border border-dashed border-gray-300 bg-white p-6 text-center">
                <p className="text-sm font-medium text-gray-700">
                  No open stockout alerts.
                </p>

                <p className="mt-1 text-xs text-gray-500">
                  Everything currently looks clear.
                </p>
              </div>
            )}

          {!loading &&
            !error &&
            alerts.length > 0 && (
              <div className="space-y-3">
                {alerts.map((alert) => {
                  const critical =
                    alert.severity === "CRITICAL";

                  return (
                    <article
                      key={alert.id}
                      className={`rounded-xl border p-4 shadow-sm ${
                        critical
                          ? "border-red-200 bg-red-50"
                          : "border-amber-200 bg-amber-50"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                                critical
                                  ? "bg-red-100 text-red-800"
                                  : "bg-amber-100 text-amber-800"
                              }`}
                            >
                              {alert.severity}
                            </span>

                            <span className="text-sm font-semibold text-gray-900">
                              {alert.product_id}
                            </span>
                          </div>

                          <p className="mt-2 text-sm leading-5 text-gray-700">
                            {alert.message}
                          </p>

                          <div className="mt-3 space-y-1 text-xs text-gray-500">
                            <p>
                              Projected inventory:{" "}
                              <span className="font-semibold text-gray-700">
                                {alert.projected_inventory.toFixed(
                                  0
                                )}
                              </span>
                            </p>

                            <p>
                              Forecast lead-time demand:{" "}
                              <span className="font-semibold text-gray-700">
                                {alert.forecast_lead_time_demand.toFixed(
                                  0
                                )}
                              </span>
                            </p>

                            <p>
                              {new Date(
                                alert.created_at
                              ).toLocaleString()}
                            </p>
                          </div>
                        </div>

                        <button
                          type="button"
                          onClick={() =>
                            handleAcknowledge(
                              alert.id
                            )
                          }
                          disabled={
                            busyId === alert.id
                          }
                          className="shrink-0 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {busyId === alert.id
                            ? "Saving…"
                            : "Acknowledge"}
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
        </div>

        {/* Footer */}
        <footer className="shrink-0 border-t border-gray-200 bg-white px-5 py-4">
          <Link
            to="/stockout"
            onClick={onClose}
            className="text-sm font-medium text-brand-700 hover:underline"
          >
            View Stockout Risk →
          </Link>
        </footer>
      </section>
    </div>
  );
}