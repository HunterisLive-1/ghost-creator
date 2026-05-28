import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { globalStyles } from "./theme/globalStyles";

// Global crash reporting overlay
window.addEventListener("error", (event) => {
  const container = document.createElement("div");
  container.style.position = "fixed";
  container.style.top = "0";
  container.style.left = "0";
  container.style.width = "100vw";
  container.style.height = "100vh";
  container.style.backgroundColor = "rgba(20, 0, 0, 0.95)";
  container.style.color = "#FF1744";
  container.style.padding = "20px";
  container.style.zIndex = "999999";
  container.style.fontFamily = "monospace";
  container.style.fontSize = "14px";
  container.style.overflow = "auto";
  container.style.boxSizing = "border-box";
  container.innerHTML = `
    <h1 style="color: #FF5252; margin-top: 0; font-size: 20px;">🔴 Runtime Crash Detected!</h1>
    <p><strong>Message:</strong> ${event.message}</p>
    <p><strong>Filename:</strong> ${event.filename}</p>
    <p><strong>Line/Col:</strong> ${event.lineno}:${event.colno}</p>
    <p><strong>Stack Trace:</strong></p>
    <pre style="background: rgba(0,0,0,0.5); padding: 15px; border-radius: 4px; color: #ff8a80; overflow-x: auto; white-space: pre-wrap;">${event.error?.stack || "No stack trace available"}</pre>
    <button onclick="window.location.reload()" style="background: #FF5252; color: white; border: none; padding: 10px 20px; font-weight: bold; cursor: pointer; border-radius: 4px;">Reload Page</button>
  `;
  document.body.appendChild(container);
});

window.addEventListener("unhandledrejection", (event) => {
  const container = document.createElement("div");
  container.style.position = "fixed";
  container.style.top = "0";
  container.style.left = "0";
  container.style.width = "100vw";
  container.style.height = "100vh";
  container.style.backgroundColor = "rgba(20, 0, 0, 0.95)";
  container.style.color = "#FF1744";
  container.style.padding = "20px";
  container.style.zIndex = "999999";
  container.style.fontFamily = "monospace";
  container.style.fontSize = "14px";
  container.style.overflow = "auto";
  container.style.boxSizing = "border-box";
  const reason = event.reason;
  container.innerHTML = `
    <h1 style="color: #FF5252; margin-top: 0; font-size: 20px;">🔴 Unhandled Promise Rejection!</h1>
    <p><strong>Reason:</strong> ${reason}</p>
    <p><strong>Stack Trace:</strong></p>
    <pre style="background: rgba(0,0,0,0.5); padding: 15px; border-radius: 4px; color: #ff8a80; overflow-x: auto; white-space: pre-wrap;">${reason?.stack || "No stack trace available"}</pre>
    <button onclick="window.location.reload()" style="background: #FF5252; color: white; border: none; padding: 10px 20px; font-weight: bold; cursor: pointer; border-radius: 4px;">Reload Page</button>
  `;
  document.body.appendChild(container);
});

const style = document.createElement("style");
style.textContent = globalStyles;
document.head.appendChild(style);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
