import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: Vite serves :3000 and proxies /api + /metrics to the AIOS backend on
// :8787 (same-origin, no CORS). SSE streams pass through without buffering.
// Prod: `npm run build` emits ../ui/dist, served live at request time by the
// Python server (api/server.py resolves ui/dist/index.html per request via
// _serve_static — never snapshotted at import, so a fresh build is picked up
// without restarting the process).
export default defineConfig({
  plugins: [react(), tailwindcss()],
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
