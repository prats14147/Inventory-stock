import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import Nav from "./components/Nav";
import Account from "./pages/Account";
import Dashboard from "./pages/Dashboard";
import Forecast from "./pages/Forecast";
import Inventory from "./pages/Inventory";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Reorder from "./pages/Reorder";
import ResetPassword from "./pages/ResetPassword";
import Sales from "./pages/Sales";
import Settings from "./pages/Settings";
import Stockout from "./pages/Stockout";
import Watchlist from "./pages/Watchlist";
import Chatbot from "./pages/Chatbot";
import { getAccessToken, getCurrentUser, setAccessToken, signOut } from "./services/api";
import type { AuthUser } from "./services/api";

function PublicPages({ onSignedIn }: { onSignedIn: (user: AuthUser) => void }) {
  const [showLogin, setShowLogin] = useState(false);
  const navigate = useNavigate();
  return (
    <Routes>
      <Route path="/login" element={<Login onSuccess={onSignedIn} onForgotPassword={() => navigate("/forgot-password")} onBack={() => navigate("/")} />} />
      <Route path="/forgot-password" element={<ResetPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="*" element={showLogin ? <Login onSuccess={onSignedIn} onForgotPassword={() => navigate("/forgot-password")} onBack={() => setShowLogin(false)} /> : <Landing onLogin={() => setShowLogin(true)} />} />
    </Routes>
  );
}

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checking, setChecking] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    let alive = true;
    const check = async () => {
      if (!getAccessToken()) { if (alive) { setUser(null); setChecking(false); } return; }
      try { const current = await getCurrentUser(); if (alive) setUser(current); }
      catch { if (alive) { setAccessToken(null); setUser(null); } }
      finally { if (alive) setChecking(false); }
    };
    void check();
    const changed = () => {
      if (!getAccessToken()) { setUser(null); setChecking(false); }
      else void check();
    };
    window.addEventListener("inventoryai:auth-changed", changed);
    return () => { alive = false; window.removeEventListener("inventoryai:auth-changed", changed); };
  }, []);

  async function finishSignIn(signedInUser: AuthUser) {
    setUser(signedInUser);
    navigate(signedInUser.must_change_password ? "/account" : "/");
  }

  async function finishSignOut() {
    try { await signOut(); } catch { /* The local session is cleared even if the API is unavailable. */ }
    setAccessToken(null);
    setUser(null);
    navigate("/");
  }

  if (checking) return <div className="p-8 text-center text-sm text-gray-500">Checking your sign-in…</div>;
  if (!user) return <PublicPages onSignedIn={finishSignIn} />;

  return (
    <div className="min-h-screen bg-gray-50">
      <Nav user={user} onSignOut={() => void finishSignOut()} />
      <main className="mx-auto max-w-6xl px-4 py-6">
        {user.must_change_password ? <Account user={user} onUserChange={setUser} onPasswordChanged={() => void finishSignOut()} /> : (
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/inventory" element={<Inventory />} />
            <Route path="/sales" element={<Sales />} />
            <Route path="/forecast" element={<Forecast />} />
            <Route path="/stockout" element={<Stockout />} />
            <Route path="/reorder" element={<Reorder />} />
            <Route path="/watchlist" element={<Watchlist />} />
            {user.role === "admin" && <Route path="/settings" element={<Settings />} />}
            {user.role !== "viewer" && <Route path="/chat" element={<Chatbot />} />}
            <Route path="/account" element={<Account user={user} onUserChange={setUser} onPasswordChanged={() => void finishSignOut()} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
      </main>
    </div>
  );
}
