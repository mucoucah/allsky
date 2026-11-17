import { FormEvent, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

export default function Login() {
  const qc = useQueryClient();
  const [user, setUser] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.login(user, password);
      await qc.invalidateQueries({ queryKey: ["whoami"] });
    } catch {
      setError("Those credentials were not accepted.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-full flex items-center justify-center p-6">
      <form onSubmit={onSubmit} className="card w-full max-w-sm flex flex-col gap-3">
        <h1 className="text-lg font-semibold">Allsky</h1>
        <p className="text-sm text-ink-muted">Sign in to the camera.</p>
        <label className="text-xs text-ink-dim">
          Username
          <input
            className="mt-1 w-full rounded-lg bg-bg-base border border-bg-raised px-3 py-2 text-sm text-ink"
            value={user}
            onChange={(e) => setUser(e.target.value)}
            autoComplete="username"
          />
        </label>
        <label className="text-xs text-ink-dim">
          Password
          <input
            type="password"
            className="mt-1 w-full rounded-lg bg-bg-base border border-bg-raised px-3 py-2 text-sm text-ink"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error && <div className="text-sm text-err">{error}</div>}
        <button
          type="submit"
          disabled={busy || !user || !password}
          className="px-3 py-2 rounded-lg bg-accent text-bg-base text-sm font-medium disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
