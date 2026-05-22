import { theme } from "./tokens";

export const globalStyles = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html, body, #root { height: 100%; width: 100%; overflow: hidden; }
  body {
    font-family: "Segoe UI", system-ui, sans-serif;
    background: ${theme.bgMain};
    color: ${theme.textPri};
    -webkit-font-smoothing: antialiased;
  }
  button { cursor: pointer; font-family: inherit; }
  input, textarea, select {
    font-family: "Consolas", "Share Tech Mono", monospace;
    background: ${theme.bgSec};
    color: ${theme.textPri};
    border: 1px solid ${theme.border};
    border-radius: 4px;
    padding: 8px 10px;
  }
  input:focus, textarea:focus, select:focus {
    outline: none;
    border-color: ${theme.accentPri};
  }
  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-track { background: ${theme.bgMain}; }
  ::-webkit-scrollbar-thumb { background: ${theme.border}; border-radius: 4px; }
`;
