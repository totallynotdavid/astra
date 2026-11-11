import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

import { chromium, type Browser, type Locator, type Page } from "playwright-core";
import { preview, type PreviewServer } from "vite";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const root = resolve(import.meta.dirname, "..");
const outDir = "dist-site";

let server: PreviewServer;
let browser: Browser;
let page: Page;
let url: string;
const backendRequests: string[] = [];

beforeAll(async () => {
  execFileSync("uv", ["run", "python", "-m", "astra.export"], {
    cwd: resolve(root, "../server"),
    stdio: "inherit",
  });
  execFileSync("bun", ["run", "build:site"], { cwd: root, stdio: "inherit" });
  server = await preview({
    configFile: false,
    root,
    build: { outDir },
    preview: { host: "127.0.0.1", port: 0 },
  });
  url = server.resolvedUrls?.local[0] ?? "";
  browser = await chromium.launch();
  page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.on("request", (request) => {
    const { pathname, protocol } = new URL(request.url());
    if (pathname.startsWith("/api/") || pathname === "/health" || protocol.startsWith("ws")) {
      backendRequests.push(request.url());
    }
  });
});

afterAll(async () => {
  await browser?.close();
  await server?.close();
});

async function open(hash: string) {
  await page.evaluate((next) => {
    location.hash = next;
  }, hash);
}

async function see(locator: Locator) {
  await locator.first().waitFor({ state: "visible", timeout: 5000 });
}

async function count(locator: Locator, expected: number) {
  await expect.poll(() => locator.count(), { timeout: 5000 }).toBe(expected);
}

describe("the published demo, read from static files with no server", () => {
  it("walks the crew overview, a profile, an alert with its trail and each lab screen", async () => {
    await page.goto(url);

    const cards = page.getByRole("link", { name: /^AZ-\d/ });
    await cards.first().waitFor();
    await count(cards, 4);
    await count(page.getByText("Grabación"), 4);
    await see(page.getByText("Simulado").first());

    await page.getByRole("link", { name: /Valeria Ramos/ }).click();
    await page.getByRole("heading", { name: "Valeria Ramos" }).waitFor();
    await see(page.getByText("Patrón de posible caída"));
    await see(page.getByText("Hallazgos por modalidad"));
    await see(page.getByText(/Gráfica de frecuencia cardíaca de los últimos 4 minutos/));
    await count(page.getByLabel("Periodo de la evaluación"), 0);

    await open("#/alerts");
    await page.getByRole("heading", { name: "Historial de revisiones" }).waitFor();
    await see(page.getByText("Ejemplo de revisión: el médico vio"));
    await count(page.getByRole("button", { name: "Registrar revisión" }), 0);

    await open("#/vision");
    await page.getByRole("heading", { name: "Línea de tiempo" }).waitFor();
    await see(page.getByText("Inactividad prolongada").first());
    await see(page.getByText("La entrada es simulada").first());

    await open("#/audio");
    await page.getByRole("heading", { name: "Línea de tiempo" }).waitFor();
    await see(page.getByText("Interrupciones frecuentes"));
    await page
      .getByRole("button", { name: /1 hallazgo/ })
      .first()
      .click();
    await see(page.getByText("Frase de alarma explícita"));

    await open("#/evaluation");
    await page.getByRole("heading", { name: "Cómo se calcula" }).waitFor();
    await count(page.getByRole("table"), 2);
    await count(page.getByText("Señales falsas: 0."), 2);

    expect(backendRequests).toEqual([]);
  });
});
