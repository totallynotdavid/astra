import type { components } from "../contract/api";
import type { User } from "./source";

export class LoginRefused extends Error {
  constructor() {
    super("Usuario o contraseña incorrectos.");
  }
}

export interface AuthApi {
  me(): Promise<User | null>;
  login(username: string, password: string): Promise<User>;
  logout(): Promise<void>;
}

export function createAuthApi(): AuthApi {
  return {
    async me() {
      const response = await fetch("/api/v1/auth/me");
      if (response.status === 401) return null;
      if (!response.ok) throw new Error(`GET /api/v1/auth/me respondió ${response.status}`);
      return (await response.json()) as User;
    },
    async login(username, password) {
      const body: components["schemas"]["LoginRequest"] = { username, password };
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (response.status === 401 || response.status === 422) throw new LoginRefused();
      if (!response.ok) throw new Error(`POST /api/v1/auth/login respondió ${response.status}`);
      return (await response.json()) as User;
    },
    async logout() {
      await fetch("/api/v1/auth/logout", { method: "POST" });
    },
  };
}
