import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { selectSource } from "./data";
import { CrewStore } from "./data/crew";
import { combineSinks } from "./data/source";
import { DashboardStore } from "./data/store";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root element");

const store = new DashboardStore();
const crew = new CrewStore();
const source = selectSource();
source.start(combineSinks(store, crew));

createRoot(root).render(
  <StrictMode>
    <App store={store} crew={crew} source={source} />
  </StrictMode>,
);
