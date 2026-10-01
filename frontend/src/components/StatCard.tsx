// frontend/src/components/StatCard.tsx

interface StatCardProps {
  label: string;
  value: string | number;
  accent?: "default" | "warning" | "danger";
}

const accentClasses: Record<NonNullable<StatCardProps["accent"]>, string> = {
  default: "border-gray-200",
  warning: "border-amber-400",
  danger: "border-red-400",
};

export default function StatCard({ label, value, accent = "default" }: StatCardProps) {
  return (
    <div className={`rounded-lg border bg-white p-4 shadow-sm ${accentClasses[accent]}`}>
      <p className="text-sm text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-gray-900">{value}</p>
    </div>
  );
}
