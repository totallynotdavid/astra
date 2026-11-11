// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Root } from "./Root";
import type { Backend } from "./data";
import { LoginRefused, type AuthApi } from "./data/auth";
import type { AstraSource, Sink, User } from "./data/source";

afterEach(() => {
  cleanup();
  location.hash = "";
});

const doctor: User = {
  id: "u1",
  username: "doctor",
  role: "doctor",
  crew_member_id: null,
  active: true,
  created_at: "2026-11-11T10:00:00Z",
};

function emptySource(onStop: () => void = () => {}): AstraSource {
  return {
    name: "test",
    speeds: [1],
    replayOnly: false,
    crew: null,
    start(sink: Sink) {
      sink.ready({
        health: null,
        devices: [],
        sessions: [],
        events: [],
        readings: [],
        insights: [],
      });
      sink.syncCrew?.({ members: [], alerts: [], latest: {}, findings: {} });
    },
    stop: onStop,
    startReplay: vi.fn(),
  };
}

function backendWith(auth: AuthApi, sources: AstraSource[] = []): Backend {
  return {
    auth,
    user: null,
    createSource: () => {
      const source = emptySource();
      sources.push(source);
      return source;
    },
  };
}

describe("sign in", () => {
  it("asks for credentials when there is no session, then opens the workspace", async () => {
    const login = vi.fn(async () => doctor);
    const auth: AuthApi = { me: async () => null, login, logout: vi.fn() };
    render(<Root backend={backendWith(auth)} />);

    await screen.findByRole("heading", { name: "Iniciar sesión" });
    fireEvent.change(screen.getByLabelText("Usuario"), { target: { value: " doctor " } });
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "secreto-1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Iniciar sesión" }));

    await screen.findByRole("button", { name: "Cerrar sesión" });
    expect(login).toHaveBeenCalledWith("doctor", "secreto-1234");
    expect(screen.getByText("Médico")).toBeTruthy();
  });

  it("keeps the user name and clears the password after a refusal", async () => {
    const auth: AuthApi = {
      me: async () => null,
      login: async () => {
        throw new LoginRefused();
      },
      logout: vi.fn(),
    };
    render(<Root backend={backendWith(auth)} />);

    await screen.findByLabelText("Usuario");
    fireEvent.change(screen.getByLabelText("Usuario"), { target: { value: "doctor" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "mala" } });
    fireEvent.click(screen.getByRole("button", { name: "Iniciar sesión" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("El usuario o la contraseña no coinciden");
    expect((screen.getByLabelText("Usuario") as HTMLInputElement).value).toBe("doctor");
    expect((screen.getByLabelText("Contraseña") as HTMLInputElement).value).toBe("");
  });

  it("goes straight to the workspace when the session is still valid", async () => {
    const auth: AuthApi = { me: async () => doctor, login: vi.fn(), logout: vi.fn() };
    render(<Root backend={backendWith(auth)} />);
    await screen.findByRole("button", { name: "Cerrar sesión" });
    expect(screen.queryByLabelText("Contraseña")).toBeNull();
  });
});

describe("sign out", () => {
  it("stops the source and shows the sign in screen", async () => {
    const logout = vi.fn(async () => {});
    const stop = vi.fn();
    const auth: AuthApi = { me: async () => doctor, login: vi.fn(), logout };
    const backend: Backend = { auth, user: null, createSource: () => emptySource(stop) };
    render(<Root backend={backend} />);

    fireEvent.click(await screen.findByRole("button", { name: "Cerrar sesión" }));

    await screen.findByLabelText("Contraseña");
    expect(logout).toHaveBeenCalledOnce();
    expect(stop).toHaveBeenCalled();
  });

  it("returns to the sign in screen when the server ends the session", async () => {
    let end: () => void = () => {};
    const auth: AuthApi = { me: async () => doctor, login: vi.fn(), logout: vi.fn() };
    const backend: Backend = {
      auth,
      user: null,
      createSource: (onSessionEnd) => {
        end = onSessionEnd;
        return emptySource();
      },
    };
    render(<Root backend={backend} />);
    await screen.findByRole("button", { name: "Cerrar sesión" });

    end();

    await waitFor(() => expect(screen.getByLabelText("Contraseña")).toBeTruthy());
  });
});

describe("no accounts", () => {
  it("opens the workspace as the fixed user, with no sign out", async () => {
    const jury: User = { ...doctor, username: "jurado", role: "jury" };
    const backend: Backend = { auth: null, user: jury, createSource: () => emptySource() };
    render(<Root backend={backend} />);
    await screen.findByText("Jurado");
    expect(screen.queryByRole("button", { name: "Cerrar sesión" })).toBeNull();
    expect(screen.queryByLabelText("Contraseña")).toBeNull();
  });
});
