import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { globalStyles } from "./theme/globalStyles";

const style = document.createElement("style");
style.textContent = globalStyles;
document.head.appendChild(style);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
