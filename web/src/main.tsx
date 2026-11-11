import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { Root } from "./Root";
import { selectBackend } from "./data";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root element");

createRoot(root).render(
  <StrictMode>
    <Root backend={selectBackend()} />
  </StrictMode>,
);
