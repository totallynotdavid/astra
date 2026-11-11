import type { Health } from "./contract";

export type Tone = "success" | "review" | "critical";

export interface HealthLine {
  label: string;
  value: string;
  tone: Tone;
}

const serial: Record<Health["serial"], [string, Tone]> = {
  connected: ["Conectado", "success"],
  stale: ["Sin datos recientes", "review"],
  disconnected: ["Desconectado", "critical"],
};

const model: Record<Health["model"], [string, Tone]> = {
  ready: ["Disponible", "success"],
  unavailable: ["Modelo no disponible", "review"],
};

const storage: Record<Health["storage"], [string, Tone]> = {
  ok: ["Disponible", "success"],
  error: ["Con error", "critical"],
};

export function describeHealth(health: Health): HealthLine[] {
  const line = (label: string, [value, tone]: [string, Tone]) => ({ label, value, tone });
  return [
    line("Sensor ESP32", serial[health.serial]),
    line("Análisis automático", model[health.model]),
    line("Almacenamiento", storage[health.storage]),
  ];
}

export async function fetchHealth(signal?: AbortSignal): Promise<Health> {
  const response = await fetch("/health", { signal });
  if (!response.ok) throw new Error(`GET /health answered ${response.status}`);
  return (await response.json()) as Health;
}
