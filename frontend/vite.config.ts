import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: Vite serves localhost:3000 and proxies /api + /metrics to the AIOS
// backend on :8787 (same-origin, no CORS). SSE streams pass through cleanly.
// Prod: `npm run build` emits static assets consumed by the Python server.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8787",
        changeOrigin: false,
        // SSE: never buffer the stream
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            proxyReq.setHeader("Accept", "text/event-stream, application/json");
          });
        },
      },
      "/metrics": "http://127.0.0.1:8787",
    },
  },
  build: {
    outDir: "../ui/dist",
    emptyOutDir: true,
    sourcemap: false,
    target: "es2022",
    chunkSizeWarningLimit: 900,
  },
});
