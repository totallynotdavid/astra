import { describe, expect, it } from "vitest";

import { describeHealth } from "./health";

describe("describeHealth", () => {
  it("names every part of the service in Spanish with its tone", () => {
    const lines = describeHealth({
      schema_version: "1.0",
      serial: "stale",
      model: "unavailable",
      storage: "ok",
    });

    expect(lines).toEqual([
      { label: "Sensor ESP32", value: "Sin datos recientes", tone: "review" },
      { label: "Análisis automático", value: "Modelo no disponible", tone: "review" },
      { label: "Almacenamiento", value: "Disponible", tone: "success" },
    ]);
  });
});
