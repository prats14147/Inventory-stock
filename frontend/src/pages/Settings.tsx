// frontend/src/pages/Settings.tsx
//
// Admin operations knobs: supplier lead time, safety-stock factor, and the
// low-stock threshold. Stored in PostgreSQL (system_settings), env vars stay
// the defaults. Saving clears the risk cache so the next read recomputes.

import { FormEvent, useState } from "react";
import { useApi } from "../hooks/useApi";
import { ApiError, getSystemSettings, updateSystemSettings } from "../services/api";
import { LoadingState, ErrorState } from "../components/LoadingError";
import PageHeader from "../components/PageHeader";
import Card from "../components/Card";

const FIELDS = [
  { key: "default_lead_time_days", label: "Default lead time (days)", step: "1", min: 1, max: 90 },
  { key: "safety_stock_service_factor", label: "Safety-stock service factor (z-score)", step: "0.05", min: 0, max: 5 },
  { key: "low_stock_threshold", label: "Low-stock threshold (units)", step: "1", min: 1, max: 10000 },
] as const;

type FieldKey = (typeof FIELDS)[number]["key"];

export default function Settings() {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data, loading, error } = useApi(() => getSystemSettings(), [refreshKey]);
  const [values, setValues] = useState<Partial<Record<FieldKey, string>>>({});
  const [touched, setTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [success, setSuccess] = useState("");

  function displayValue(key: FieldKey): string {
    if (values[key] !== undefined) return values[key] as string;
    const current = data?.settings[key]?.value;
    return current == null ? "" : String(current);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormError("");
    setSuccess("");
    try {
      const payload: Record<string, number> = {};
      for (const { key } of FIELDS) {
        const raw = displayValue(key);
        if (raw.trim() === "") throw new Error(`Enter a value for every setting.`);
        const num = Number(raw);
        if (!Number.isFinite(num)) throw new Error(`"${raw}" is not a valid number.`);
        payload[key] = num;
      }
      const res = await updateSystemSettings(payload);
      setValues({});
      setTouched(false);
      setRefreshKey((k) => k + 1);
      setSuccess("Settings saved to PostgreSQL. Risk and reorder figures will recompute on next read.");
      void res;
    } catch (err) {
      setFormError(err instanceof ApiError || err instanceof Error ? err.message : "Could not save settings.");
    } finally {
      setSaving(false);
    }
  }

  if (loading && !data) return <LoadingState label="Loading system settings..." />;
  if (error && !data) return <ErrorState message={error} />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="System Settings"
        subtitle="Operations assumptions every risk and reorder figure is built on. Edits apply immediately — no redeploy."
      />

      <Card title="Inventory policy" subtitle="A row in system_settings overrides the environment default.">
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            {FIELDS.map(({ key, label, step, min, max }) => {
              const meta = data?.settings[key];
              return (
                <label key={key} className="space-y-1 text-sm font-medium text-gray-700">
                  {label}
                  <input
                    type="number"
                    step={step}
                    min={min}
                    max={max}
                    required
                    value={displayValue(key)}
                    onChange={(e) => {
                      setValues((v) => ({ ...v, [key]: e.target.value }));
                      setTouched(true);
                      setSuccess("");
                    }}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 font-normal tabular-nums"
                  />
                  <span className="block text-xs font-normal text-gray-500">
                    {meta?.description ?? ""}
                    <br />
                    Source: <span className={`font-semibold ${meta?.source === "database" ? "text-brand-700" : "text-gray-500"}`}>{meta?.source ?? "—"}</span>
                    {" · "}default {meta?.default ?? "—"}
                  </span>
                </label>
              );
            })}
          </div>

          {formError && <p role="alert" className="text-sm text-red-700">{formError}</p>}
          {success && <p role="status" className="text-sm text-green-700">{success}</p>}

          <button
            type="submit"
            disabled={saving || !touched}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save settings"}
          </button>
        </form>
      </Card>

      <p className="text-xs text-gray-400">
        Lead time is an assumption, not a measured supplier SLA — this dataset has no real supplier lead time
        (see docs/limitations.md). The safety-stock factor multiplies the product's historical daily-demand
        standard deviation.
      </p>
    </div>
  );
}
