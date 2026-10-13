import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, confirmPasswordReset, requestPasswordReset } from "../services/api";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setMessage(""); setBusy(true);
    try {
      if (token) {
        const result = await confirmPasswordReset(token, password);
        setMessage(result.message);
      } else {
        const result = await requestPasswordReset(email);
        setMessage(result.email_delivery_configured ? result.message : "The request was received, but email delivery is not configured on this server. Contact your administrator to enable SMTP or reset the account.");
      }
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Could not complete the request.");
    } finally { setBusy(false); }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-10">
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-7 shadow-xl">
        <Link to="/login" className="text-sm font-medium text-brand-700 hover:underline">← Back to sign in</Link>
        <h1 className="mt-5 text-2xl font-semibold text-gray-900">{token ? "Choose a new password" : "Reset your password"}</h1>
        <p className="mt-2 text-sm leading-6 text-gray-500">{token ? "Use at least 12 characters. Reset links expire after 30 minutes." : "Enter your account email and we’ll send a one-time reset link if an active account matches."}</p>
        {token ? (
          <label className="mt-6 block text-sm font-medium text-gray-700">New password
            <input type="password" autoComplete="new-password" minLength={12} required value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal" />
          </label>
        ) : (
          <label className="mt-6 block text-sm font-medium text-gray-700">Email address
            <input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal" />
          </label>
        )}
        {message && <p role="status" className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">{message}</p>}
        {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        <button disabled={busy} className="mt-6 w-full rounded-lg bg-brand-600 px-4 py-2.5 font-medium text-white hover:bg-brand-700 disabled:opacity-60">{busy ? "Please wait…" : token ? "Set new password" : "Send reset link"}</button>
      </form>
    </main>
  );
}
