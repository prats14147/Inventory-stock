// frontend/src/pages/ModelHealth.tsx
//
// Training metrics for the XGBoost demand models, read from the saved
// artifacts via /api/model-health (MAE, RMSE, sMAPE, splits, features).

import { useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { useApi } from "../hooks/useApi";
import { getModelHealth } from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";
import StatCard from "../components/StatCard";

export default function ModelHealth() {
  const { data, loading, error } = useApi(() => getModelHealth(), []);
  const [showFeatures, setShowFeatures] = useState<number | null>(null);

  if (loading) return <LoadingState label="Loading model health..." />;
  if (error) return <ErrorState message={error} />;

  const horizons = data?.horizons ?? [];
  const maeCompare = horizons.map((h) => ({
    horizon: `${h.horizon_days}-day`,
    Model: Number(h.mae.toFixed(1)),
    Baseline: Number(h.baseline_mae.toFixed(1)),
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Model Health"
        subtitle={
          data?.artifacts_found
            ? `XGBoost demand models at 7 and 14 days, evaluated on a chronological test holdout.`
            : "No training artifacts found — run the training pipeline first."
        }
      />

      {!data?.artifacts_found && (
        <Card title="No artifacts">
          <p className="text-sm text-gray-600">
            Expected <code className="font-mono">ml/artifacts/forecast_summary.json</code> next to the backend
            (looked in <code className="font-mono">{data?.artifacts_dir}</code>). Train the models, then reload.
          </p>
        </Card>
      )}

      {horizons.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {horizons.map((h) => (
            <StatCard
              key={h.horizon_days}
              label={`${h.horizon_days}-day test MAE`}
              value={h.mae.toFixed(1)}
              hint={`Baseline ${h.baseline_mae.toFixed(1)} · ${h.improvement_pct_vs_baseline != null ? `${h.improvement_pct_vs_baseline}% better` : "—"}`}
              accent="info"
            />
          ))}
          <StatCard
            label="Test sMAPE"
            value={horizons.map((h) => `${h.horizon_days}d: ${h.smape.toFixed(0)}%`).join(" · ")}
            hint="High — limited learnable signal in synthetic data"
            accent="warning"
          />
          <StatCard
            label="Test rows"
            value={(horizons[0]?.test_rows ?? 0).toLocaleString()}
            hint={`Train ${((horizons[0]?.train_rows ?? 0) / 1000).toFixed(1)}k · Val ${((horizons[0]?.val_rows ?? 0) / 1000).toFixed(1)}k`}
          />
        </div>
      )}

      {maeCompare.length > 0 && (
        <Card title="Model vs baseline MAE" subtitle="Lower is better · test set">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={maeCompare}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="horizon" fontSize={12} tickLine={false} axisLine={{ stroke: "#e5e7eb" }} />
              <YAxis fontSize={12} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: "#eff6ff" }} />
              <Bar dataKey="Model" fill="#2563eb" radius={[6, 6, 0, 0]} />
              <Bar dataKey="Baseline" fill="#9ca3af" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {horizons.map((h) => (
        <Card
          key={h.horizon_days}
          title={`${h.horizon_days}-day horizon detail`}
          subtitle={`Train < ${h.train_date_cutoff} · Val ${h.train_date_cutoff}–${h.val_date_cutoff} · Test ≥ ${h.val_date_cutoff}`}
          actions={
            <button
              type="button"
              onClick={() => setShowFeatures(showFeatures === h.horizon_days ? null : h.horizon_days)}
              className="rounded-lg border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              {showFeatures === h.horizon_days ? "Hide features" : `Show ${h.feature_count} features`}
            </button>
          }
        >
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div><dt className="text-xs uppercase text-gray-500">RMSE</dt><dd className="font-semibold tabular-nums">{h.rmse.toFixed(1)} <span className="font-normal text-gray-500">(base {h.baseline_rmse.toFixed(1)})</span></dd></div>
            <div><dt className="text-xs uppercase text-gray-500">sMAPE</dt><dd className="font-semibold tabular-nums">{h.smape.toFixed(1)}% <span className="font-normal text-gray-500">(base {h.baseline_smape.toFixed(1)}%)</span></dd></div>
            <div><dt className="text-xs uppercase text-gray-500">Best iteration</dt><dd className="font-semibold tabular-nums">{h.best_iteration}</dd></div>
            <div><dt className="text-xs uppercase text-gray-500">Test rows</dt><dd className="font-semibold tabular-nums">{h.test_rows.toLocaleString()}</dd></div>
          </dl>
          {showFeatures === h.horizon_days && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {h.feature_columns.map((f) => (
                <code key={f} className="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs text-gray-700">{f}</code>
              ))}
            </div>
          )}
        </Card>
      ))}

      {data?.note && <p className="text-xs text-gray-500">{data.note}</p>}
    </div>
  );
}
