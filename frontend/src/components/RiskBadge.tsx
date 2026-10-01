// frontend/src/components/RiskBadge.tsx

import type { RiskLevel } from "../types/stockout";

const styles: Record<RiskLevel, string> = {
  LOW: "bg-green-100 text-green-800",
  MEDIUM: "bg-amber-100 text-amber-800",
  HIGH: "bg-red-100 text-red-800",
};

export default function RiskBadge({ risk }: { risk: RiskLevel }) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[risk]}`}>{risk}</span>
  );
}
