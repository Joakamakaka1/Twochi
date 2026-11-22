import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App, wire } from "./app";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("Missing #root element");
}

const wiring = wire();

createRoot(root).render(
  <StrictMode>
    <App wiring={wiring} />
  </StrictMode>,
);
