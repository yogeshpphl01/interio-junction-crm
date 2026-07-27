/*
  <module name="vite.config" layer="frontend-build">
    <purpose>
      Vite build configuration. Replaces the old Create-React-App (react-scripts
      + craco) toolchain, which pulled an unfixable ajv/webpack dependency
      conflict. Vite is the modern, reliable bundler for this React SPA.
    </purpose>
    <notes>
      - "@/..." path alias maps to /src (same as the old craco/jsconfig alias).
      - process.env.REACT_APP_BACKEND_URL is preserved (defined at build time) so
        no application code had to change. Empty value => same-origin "/api",
        which nginx proxies to the backend.
      - Output goes to /build so the existing Dockerfile + nginx copy still work.
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
  // Treat JSX inside plain .js files as JSX (a few legacy files use it).
  esbuild: {
    loader: "jsx",
    include: /src\/.*\.jsx?$/,
    exclude: [],
  },
  optimizeDeps: {
    esbuildOptions: {
      loader: { ".js": "jsx" },
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
    port: 3000,
  },
});
