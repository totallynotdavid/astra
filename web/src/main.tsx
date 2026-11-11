import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { selectSource } from "./data";
import { DashboardStore } from "./data/store";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root element");

const store = new DashboardStore();
const source = selectSource();
source.start(store);

createRoot(root).render(
  <StrictMode>
    <App store={store} source={source} />
  </StrictMode>,
);
