import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import Card from "../components/Card";
import { ApiError, changeMyPassword, createManagedUser, listManagedUsers, updateManagedUser, updateMyProfile } from "../services/api";
import type { AccountRole, AuthUser } from "../services/api";

const roles: AccountRole[] = ["admin", "manager", "viewer"];

export default function Account({ user, onUserChange, onPasswordChanged }: { user: AuthUser; onUserChange: (user: AuthUser) => void; onPasswordChanged: () => void }) {
  const [displayName, setDisplayName] = useState(user.display_name);
  const [email, setEmail] = useState(user.email);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [team, setTeam] = useState<AuthUser[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [newAccount, setNewAccount] = useState({ username: "", email: "", display_name: "", role: "viewer" as AccountRole, temporary_password: "" });

  async function refreshTeam() {
    if (user.role === "admin") {
      try { setTeam((await listManagedUsers()).users); }
      catch (reason) { setError(reason instanceof ApiError ? reason.message : "Could not load accounts."); }
    }
  }
  useEffect(() => { void refreshTeam(); }, [user.role]);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setNotice(""); setBusy(true);
    try { const updated = await updateMyProfile({ display_name: displayName, email }); onUserChange(updated); setNotice("Profile updated."); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "Could not update profile."); }
    finally { setBusy(false); }
  }
  async function savePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setNotice(""); setBusy(true);
    try { await changeMyPassword({ current_password: currentPassword, new_password: newPassword }); setNotice("Password changed. Please sign in again."); window.setTimeout(onPasswordChanged, 1000); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "Could not change password."); }
    finally { setBusy(false); }
  }
  async function addAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setNotice(""); setBusy(true);
    try {
      await createManagedUser(newAccount);
      setNewAccount({ username: "", email: "", display_name: "", role: "viewer", temporary_password: "" });
      setNotice("Account created. The user must change the temporary password after signing in."); await refreshTeam();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Could not create account."); }
    finally { setBusy(false); }
  }

  async function changeUser(userId: number, payload: { role?: AccountRole; is_active?: boolean }) {
    setError(""); setNotice("");
    try { await updateManagedUser(userId, payload); await refreshTeam(); setNotice("Account updated."); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "Could not update account."); }
  }

  return (
    <div className="space-y-5">
      <header><p className="text-sm font-medium text-brand-700">Workspace access</p><h1 className="mt-1 text-2xl font-semibold text-gray-900">Account & access</h1><p className="mt-1 text-sm text-gray-500">Update your profile and password{user.role === "admin" ? ", or manage who can use the workspace." : "."}</p></header>
      {user.must_change_password && <div role="alert" className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">Your administrator issued a temporary password. Change it before using the workspace.</div>}
      {notice && <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}
      {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card><h2 className="text-base font-semibold">Your profile</h2><p className="mt-1 text-sm text-gray-500">Signed in as <b>{user.username}</b> · {user.role}</p>
          <form onSubmit={saveProfile} className="mt-4 space-y-3">
            <label className="block text-sm font-medium text-gray-700">Display name<input required value={displayName} onChange={(e) => setDisplayName(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal" /></label>
            <label className="block text-sm font-medium text-gray-700">Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal" /></label>
            <button disabled={busy} className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">Save profile</button>
          </form>
        </Card>
        <Card><h2 className="text-base font-semibold">Change password</h2><p className="mt-1 text-sm text-gray-500">At least 12 characters. Changing it signs out your current sessions.</p>
          <form onSubmit={savePassword} className="mt-4 space-y-3">
            <label className="block text-sm font-medium text-gray-700">Current password<input type="password" autoComplete="current-password" required value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal" /></label>
            <label className="block text-sm font-medium text-gray-700">New password<input type="password" autoComplete="new-password" minLength={12} required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 font-normal" /></label>
            <button disabled={busy} className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60">Update password</button>
          </form>
        </Card>
      </div>
      {user.role === "admin" && <>
        <Card><h2 className="text-base font-semibold">Create staff account</h2><p className="mt-1 text-sm text-gray-500">New users receive a temporary password and must change it at first sign-in.</p>
          <form onSubmit={addAccount} className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <input required minLength={3} placeholder="Username" value={newAccount.username} onChange={(e) => setNewAccount({ ...newAccount, username: e.target.value })} className="rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            <input required type="email" placeholder="Email" value={newAccount.email} onChange={(e) => setNewAccount({ ...newAccount, email: e.target.value })} className="rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            <input required placeholder="Display name" value={newAccount.display_name} onChange={(e) => setNewAccount({ ...newAccount, display_name: e.target.value })} className="rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            <select value={newAccount.role} onChange={(e) => setNewAccount({ ...newAccount, role: e.target.value as AccountRole })} className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm">{roles.map((role) => <option key={role}>{role}</option>)}</select>
            <input required type="password" minLength={12} placeholder="Temporary password (12+ characters)" value={newAccount.temporary_password} onChange={(e) => setNewAccount({ ...newAccount, temporary_password: e.target.value })} className="rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            <button disabled={busy} className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">Create account</button>
          </form>
        </Card>
        <Card><div className="flex items-start justify-between"><div><h2 className="text-base font-semibold">Team accounts</h2><p className="mt-1 text-sm text-gray-500">Admins manage roles and can disable access immediately.</p></div><button onClick={() => void refreshTeam()} className="text-sm font-medium text-brand-700 hover:underline">Refresh</button></div>
          <div className="mt-4 overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="border-b text-xs uppercase text-gray-500"><tr><th className="py-2 pr-4">User</th><th className="py-2 pr-4">Role</th><th className="py-2 pr-4">Status</th><th className="py-2">Access</th></tr></thead><tbody className="divide-y">{team.map((member) => <tr key={member.id}><td className="py-3 pr-4"><div className="font-medium">{member.display_name}</div><div className="text-xs text-gray-500">{member.username} · {member.email}</div></td><td className="py-3 pr-4"><select aria-label={`Role for ${member.username}`} value={member.role} onChange={(e) => void changeUser(member.id, { role: e.target.value as AccountRole })} className="rounded border border-gray-300 bg-white px-2 py-1" disabled={member.id === user.id}>{roles.map((role) => <option key={role}>{role}</option>)}</select></td><td className="py-3 pr-4">{member.is_active ? "Active" : "Disabled"}{member.must_change_password ? " · password change required" : ""}</td><td className="py-3"><button onClick={() => void changeUser(member.id, { is_active: !member.is_active })} disabled={member.id === user.id} className="text-brand-700 hover:underline disabled:text-gray-400">{member.is_active ? "Disable" : "Enable"}</button></td></tr>)}</tbody></table></div>
        </Card>
      </>}
    </div>
  );
}
