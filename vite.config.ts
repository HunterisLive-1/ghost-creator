import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  base: "./",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    strictPort: true,
    watch: {
      ignored: [
        "**/output/**",
        "**/venv/**",
        "**/build-api/**",
        "**/dist-api/**",
        "**/build/**",
        "**/node_modules/**",
        "**/config.json",
        "**/.env.local",
        "**/.env",
        "**/*.log",
      ],
    },
  },
});
