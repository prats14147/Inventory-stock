// frontend/src/pages/Live.tsx
//
// Real-time operations page: live sales ticker + simulator controls +
// proactive stockout alerts, all streaming over WS /api/live/ws.

import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { useLiveStream } from "../hooks/useLiveStream";
import {
  ApiError,
  getLiveAlerts,
  getLiveSummary,
  getSimulatorStatus,
  runSimulatorTick,
  startSimulator,
  stopSimulator,
} from "../services/api";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import StatCard from "../components/StatCard";
import LiveFeedPanel from "../components/LiveFeedPanel";
import LiveAlertsPanel from "../components/LiveAlertsPanel";
import { LoadingState, ErrorState } from "../components/LoadingError";

export default function Live() {
  const stream = useLiveStream(15);
  const [refreshKey, setRefreshKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [simBusy, setSimBusy] = useState(false);
  const [simError, setSimError] = useState("");
  const [busyAlertId, setBusyAlertId] = useState<number | null>(null);

  const summaryQuery = useApi(() => getLiveSummary(), [refreshKey, stream.lastFrameAt]);
  const simQuery = useApi(() => getSimulatorStatus(), [refreshKey]);
  const alertsQuery = useApi(() => getLiveAlerts(false, 50), [refreshKey, stream.lastFrameAt]);

  const summary = summaryQuery.data;
  const sim = simQuery.data ?? summary?.simulator;

  // REST snapshot of open alerts (durable) merged with streamed alerts
  // (fresh). Streamed entries win on id collision.
  const streamedIds = new Set(stream.alerts.map((a) => a.id));
  const alerts = [
    ...stream.alerts,
    ...(alertsQuery.data?.alerts ?? []).filter((a) => !streamedIds.has(a.id)),
  ];

  async function tick() {
    setBusy(true);
    setSimError("");
    try {
      await runSimulatorTick(3);
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setSimError(err instanceof ApiError ? err.message : "Simulator tick failed.");
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    setSimBusy(true);
    setSimError("");
    try {
      await startSimulator(3, 3);
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setSimError(err instanceof ApiError ? err.message : "Could not start the simulator.");
    } finally {
      setSimBusy(false);
    }
  }

  async function stop() {
    setSimBusy(true);
    setSimError("");
    try {
      await stopSimulator();
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setSimError(err instanceof ApiError ? err.message : "Could not stop the simulator.");
    } finally {
      setSimBusy(false);
    }
  }

  async function acknowledge(alertId: number) {
    setBusyAlertId(alertId);
    try {
      await stream.acknowledge(alertId);
      setRefreshKey((k) => k + 1);
    } catch {
      // useLiveStream already removes optimistically on success only;
      // a failure leaves the row in place for retry.
    } finally {
      setBusyAlertId(null);
    }
  }

  return (
    <div className="space-y-6" id="live-operations">
      <PageHeader
        title="Live Operations"
        subtitle={
          stream.connected
            ? `Streaming live sales events and alerts${stream.reconnectAttempts > 0 ? ` (reconnected ${stream.reconnectAttempts}x)` : ""}.`
            : "Connecting to the live stream — REST snapshots below keep working meanwhile."
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {sim?.running ? (
              <button
                type="button"
                onClick={stop}
                disabled={simBusy}
                className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {simBusy ? "Stopping…" : "Stop simulator"}
              </button>
            ) : (
              <button
                type="button"
                onClick={start}
                disabled={simBusy}
                className="rounded-lg bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
              >
                {simBusy ? "Starting…" : "Start simulator"}
              </button>
            )}
            <button
              type="button"
              onClick={tick}
              disabled={busy}
              className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              {busy ? "Simulating…" : "Single tick"}
            </button>
          </div>
        }
      />

      {simError && <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">{simError}</p>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Simulator"
          value={sim?.running ? "Running" : "Stopped"}
          hint={sim ? `${sim.ticks} ticks · ${sim.events_per_tick}/tick` : "—"}
          accent={sim?.running ? "success" : "default"}
        />
        <StatCard label="Live events" value={(summary?.live_events ?? 0).toLocaleString()} hint={`${(stream.unitsSold || summary?.live_units_sold || 0).toLocaleString()} units sold live`} />
        <StatCard label="Open alerts" value={summary?.open_alerts ?? alerts.length} hint={`${summary?.critical_alerts ?? 0} critical`} accent={(summary?.open_alerts ?? 0) > 0 ? "danger" : "success"} />
        <StatCard label="Stream" value={stream.connected ? "Connected" : "Reconnecting"} hint={`${stream.events.length} events in view`} accent={stream.connected ? "success" : "warning"} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Live sales ticker" subtitle="Pushed over WebSocket /api/live/ws, newest first">
          <LiveFeedPanel events={stream.events} connected={stream.connected} onTick={tick} busy={busy} />
        </Card>
        <Card
          title="Stockout alerts"
          subtitle={`${alerts.length} open — acknowledge when handled`}
          actions={
            <a href="/stockout" className="text-xs font-medium text-brand-700 hover:underline">
              Open stockout risk →
            </a>
          }
        >
          {alertsQuery.loading && alerts.length === 0 ? (
            <LoadingState label="Loading alerts..." />
          ) : alertsQuery.error && alerts.length === 0 ? (
            <ErrorState message={alertsQuery.error} />
          ) : (
            <LiveAlertsPanel alerts={alerts} onAcknowledge={acknowledge} busyAlertId={busyAlertId} />
          )}
        </Card>
      </div>

      <p className="text-xs text-gray-400">
        Live traffic is synthetic (source “simulator”) and never touches the analytical tables — see docs/limitations.md.
        If the socket drops, this page falls back to polling /api/live/summary and /api/live/alerts.
      </p>
    </div>
  );
}
