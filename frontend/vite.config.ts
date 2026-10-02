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
    rollupOptions: {
      // Two independent HTML entries, deliberately sharing no chunk.
      //
      // ARCHITECTURE.txt section 8 requires the emergency commands to survive
      // model/runtime failure, and the analyst console opens an SSE stream and mounts
      // sixteen workspaces. If the operator page were a tab inside it, anything that
      // broke the console would take the kill switch with it. Two entries and no
      // manualChunks means Vite emits two independent bundles; the isolation is
      // asserted mechanically by scripts/verify_operator_isolation.py, which fails if
      // an analyst-only module name appears in the operator bundle.
      // Resolved relative to Vite's `root`, which is this directory. Not `__dirname`:
      // this config is an ES module, where `__dirname` does not exist -- the build
      // failed with an unhelpful "error during build" and no message, which is what a
      // ReferenceError inside the config looks like from the outside.
      input: {
        main: "index.html",
        operator: "operator.html",
      },
    },
  },
});
