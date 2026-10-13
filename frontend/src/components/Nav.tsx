// frontend/src/components/Nav.tsx
//
// Top navigation: sticky, with a live status dot and pill-style links so
// the active page reads instantly.

import { NavLink } from "react-router-dom";
import { AlertsBell } from "./AlertsDrawer";
import type { AuthUser } from "../services/api";

const links: { to: string; label: string; end?: boolean }[] = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/inventory", label: "Inventory" },
  { to: "/sales", label: "Sales" },
  { to: "/forecast", label: "Forecast" },
  { to: "/stockout", label: "Stockout Risk" },
  { to: "/reorder", label: "Reorder" },
  // { to: "/live", label: "Live" },
  { to: "/watchlist", label: "Watchlist" },
  // { to: "/model-health", label: "Model Health" },
];

export default function Nav({ user, onSignOut }: { user: AuthUser; onSignOut: () => void }) {
  const visibleLinks = [
    ...links,
    ...(user.role === "admin" ? [{ to: "/settings", label: "Settings" }] : []),
    ...(user.role !== "viewer" ? [{ to: "/chat", label: "Chatbot" }] : []),
    { to: "/account", label: "Account" },
  ];
  return (
    <nav className="sticky top-0 z-10 border-b border-gray-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-1 overflow-x-auto px-4 py-3">
        <span className="mr-4 flex shrink-0 items-center gap-2 font-semibold text-brand-700">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-xs font-bold text-white">
            AI
          </span>
          InventoryAI
        </span>
        {visibleLinks.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              `shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-brand-600 text-white shadow-sm"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              }`
            }
          >
            {link.label}
          </NavLink>
        ))}
        <AlertsBell />
        <span className="ml-auto shrink-0 text-xs text-gray-500">{user.display_name} · {user.role}</span>
        <button onClick={onSignOut} className="shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900">Sign out</button>
      </div>
    </nav>
  );
}
