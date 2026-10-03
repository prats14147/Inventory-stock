// frontend/src/components/RiskBadge.tsx
//
// One shared risk pill so LOW/MEDIUM/HIGH (and CRITICAL/WARNING alerts) look
// identical on every page. Colors are the single source of truth for risk.

import type { RiskLevel } from "../types/stockout";

const styles: Record<RiskLevel, string> = {
  LOW: "bg-green-100 text-green-800 ring-1 ring-inset ring-green-600/20",
  MEDIUM: "bg-amber-100 text-amber-800 ring-1 ring-inset ring-amber-600/20",
  HIGH: "bg-red-100 text-red-800 ring-1 ring-inset ring-red-600/20",
};

const dots: Record<RiskLevel, string> = {
  LOW: "bg-green-500",
  MEDIUM: "bg-amber-500",
  HIGH: "bg-red-500",
};

export default function RiskBadge({ risk }: { risk: RiskLevel }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${styles[risk]}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dots[risk]}`} />
      {risk}
    </span>
  );
}
