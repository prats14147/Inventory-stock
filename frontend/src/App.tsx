// frontend/src/App.tsx

import { useEffect, useState } from "react";
import { Routes, Route } from "react-router-dom";
import Nav from "./components/Nav";
import Dashboard from "./pages/Dashboard";
import Inventory from "./pages/Inventory";
import Sales from "./pages/Sales";
import Forecast from "./pages/Forecast";
import Stockout from "./pages/Stockout";
import Reorder from "./pages/Reorder";
import Chatbot from "./pages/Chatbot";
import Watchlist from "./pages/Watchlist";
// import ModelHealth from "./pages/ModelHealth";
import Settings from "./pages/Settings";
import Login from "./pages/Login";
import { getAccessToken, getCurrentUser, setAccessToken } from "./services/api";

export default function App() {
  const [signedIn, setSignedIn] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    const check = () => {
      if (!getAccessToken()) {
        setSignedIn(false);
        return;
      }
      getCurrentUser().then(
        () => { if (alive) setSignedIn(true); },
        () => { if (alive) { setAccessToken(null); setSignedIn(false); } },
      );
    };
    const changed = () => setSignedIn(Boolean(getAccessToken()));
    check();
    window.addEventListener("inventoryai:auth-changed", changed);
    return () => { alive = false; window.removeEventListener("inventoryai:auth-changed", changed); };
  }, []);

  if (signedIn === null) return <div className="p-8 text-center text-sm text-gray-500">Checking your sign-in…</div>;
  if (!signedIn) return <Login onSuccess={() => setSignedIn(true)} />;

  return (
    <div className="min-h-screen bg-gray-50">
      <Nav onSignOut={() => { setAccessToken(null); setSignedIn(false); }} />
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/sales" element={<Sales />} />
          <Route path="/forecast" element={<Forecast />} />
          <Route path="/stockout" element={<Stockout />} />
          <Route path="/reorder" element={<Reorder />} />

          <Route path="/watchlist" element={<Watchlist />} />

          <Route path="/settings" element={<Settings />} />
          <Route path="/chat" element={<Chatbot />} />
        </Routes>
      </main>
    </div>
  );
}
