// frontend/src/components/StatCard.tsx
//
// KPI tile with an optional status accent and helper line. The accent is a
// left border + soft tint so LOW/MEDIUM/HIGH states read at a glance while
// the number itself stays the focus.

interface StatCardProps {
  label: string;
  value: string | number;
  hint?: string;
  accent?: "default" | "success" | "warning" | "danger" | "info";
}

const accentClasses: Record<NonNullable<StatCardProps["accent"]>, string> = {
  default: "border-gray-200",
  success:
    "border-l-4 border-l-green-500 border-t-gray-200 border-r-gray-200 border-b-gray-200 bg-green-50/40",
  warning:
    "border-l-4 border-l-amber-500 border-t-gray-200 border-r-gray-200 border-b-gray-200 bg-amber-50/40",
  danger:
    "border-l-4 border-l-red-500 border-t-gray-200 border-r-gray-200 border-b-gray-200 bg-red-50/40",
  info: "border-l-4 border-l-brand-500 border-t-gray-200 border-r-gray-200 border-b-gray-200 bg-brand-50/40",
};

export default function StatCard({ label, value, hint, accent = "default" }: StatCardProps) {
  return (
    <div className={`rounded-xl border bg-white p-4 shadow-sm transition-shadow hover:shadow ${accentClasses[accent]}`}>
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-gray-900">{value}</p>
      {hint && <p className="mt-1 text-xs text-gray-500">{hint}</p>}
    </div>
  );
}
