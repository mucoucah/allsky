import { request } from "./client";

export const liveApi = {
  health: () => request<{ ok: boolean; version: string }>("/health"),
  whoami: () => request<{ authenticated: boolean; user: string | null; auth_disabled?: boolean }>("/auth/whoami"),
  login: (user: string, password: string) =>
    request<{ ok: boolean; user?: string }>("/auth/login", { method: "POST", json: { user, password } }),
};
