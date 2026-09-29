import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const API = process.env.VITE_API_PROXY || "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": { target: API, changeOrigin: false } } },
  preview: { proxy: { "/api": { target: API, changeOrigin: false } } },
  build: { sourcemap: false, chunkSizeWarningLimit: 1500 },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test-setup.ts"] },
});
