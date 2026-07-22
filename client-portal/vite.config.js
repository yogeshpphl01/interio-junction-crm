/*
  <module name="vite.config" layer="client-portal-build">
    <purpose>
      Build config for the CUSTOMER web portal — a separate app from the company
      CRM (frontend/). Same toolchain (Vite + React) so both build identically.
    </purpose>
    <notes>
      - "@/..." aliases /src.
      - REACT_APP_BACKEND_URL is defined at build time; empty => same-origin "/api",
        which the portal's own nginx proxies to the shared backend. This is what
        keeps the two apps on ONE server while each stays self-contained.
      - Output goes to /build so the Dockerfile + nginx copy match frontend/.
      - Dev server runs on 3100 (company app uses 3000) so both can run locally.
    </notes>
  </module>
*/
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  define: {
    "process.env.REACT_APP_BACKEND_URL": JSON.stringify(process.env.REACT_APP_BACKEND_URL || ""),
  },
  build: {
    outDir: "build",
    chunkSizeWarningLimit: 2000,
  },
  server: {
    host: true,
    port: 3100,
  },
});
