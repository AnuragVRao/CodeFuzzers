// Vite config for the CodeFuzzers dashboard: React plugin; /api is proxied to the analysis server; React and Recharts go into their own
// vendor chunks so no single bundle exceeds Vite's 500 kB warning limit. Output in dist/.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const proxy = { "/api": "http://127.0.0.1:8000" }; // analysis server (tools/server.py)

export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          return /node_modules\/(react|react-dom|scheduler)\//.test(id) ? "react" : "charts";
        },
      },
    },
  },
});
