import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, signIn } from "../services/api";
import type { AuthUser } from "../services/api";

export default function Login({ onSuccess, onForgotPassword, onBack }: { onSuccess: (user: AuthUser) => void; onForgotPassword: () => void; onBack: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result = await signIn(username, password);
      onSuccess(result.user);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Could not sign in. Check that the API is running.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-7 shadow-sm">
        <div className="mb-6 text-center">
          <button type="button" onClick={onBack} className="mb-5 text-sm font-medium text-brand-700 hover:underline">← InventoryAI home</button>
          <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600 font-bold text-white">AI</div>
          <h1 className="text-xl font-semibold text-gray-900">Sign in to InventoryAI</h1>
          <p className="mt-1 text-sm text-gray-500">Use the account provided by your administrator.</p>
        </div>
        <label className="mb-4 block text-sm font-medium text-gray-700">
          Username
          <input autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal" />
        </label>
        <label className="mb-5 block text-sm font-medium text-gray-700">
          Password
          <input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal" />
        </label>
        <button type="button" onClick={onForgotPassword} className="-mt-3 mb-4 text-left text-sm font-medium text-brand-700 hover:underline">Forgot password?</button>
        {error && <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        <button disabled={busy} className="w-full rounded-lg bg-brand-600 px-4 py-2.5 font-medium text-white hover:bg-brand-700 disabled:opacity-60">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
