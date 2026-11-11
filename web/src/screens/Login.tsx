import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoginRefused } from "../data/auth";

const inputClass =
  "h-11 w-full rounded-sm border border-border-strong bg-raised px-3 text-base text-text";

export function Login({
  onLogin,
}: {
  onLogin: (username: string, password: string) => Promise<void>;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const summary = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (error) summary.current?.focus();
  }, [error]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onLogin(username.trim(), password);
    } catch (err) {
      setPassword("");
      setError(
        err instanceof LoginRefused
          ? "El usuario o la contraseña no coinciden. Revísalos e inténtalo de nuevo."
          : "No se pudo conectar con el servicio. Inténtalo de nuevo en unos segundos.",
      );
      setBusy(false);
    }
  }

  return (
    <main id="main" className="mx-auto flex min-h-screen max-w-sm flex-col justify-center p-6">
      <div className="mb-6 leading-tight">
        <p className="text-base font-semibold tracking-wide">ASTRA</p>
        <p className="text-sm text-muted">Señala patrones para revisión</p>
      </div>
      <Card className="p-6">
        <h1 className="text-xl font-semibold">Iniciar sesión</h1>
        <form onSubmit={(e) => void submit(e)} className="mt-4">
          {error && (
            <p
              ref={summary}
              tabIndex={-1}
              role="alert"
              className="mb-6 rounded-sm border border-critical/40 px-3 py-2 text-sm text-critical"
            >
              {error}
            </p>
          )}
          <label htmlFor="username" className="mb-1 block text-sm text-muted">
            Usuario
          </label>
          <input
            id="username"
            name="username"
            className={inputClass}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <label htmlFor="password" className="mt-6 mb-1 block text-sm text-muted">
            Contraseña
          </label>
          <input
            id="password"
            name="password"
            type="password"
            className={inputClass}
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Button type="submit" className="mt-6" disabled={busy}>
            {busy ? "Entrando…" : "Iniciar sesión"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
