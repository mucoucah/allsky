import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite proxies /api and /api/live/ws to the FastAPI dev server so we can run
// the React dev server on :5173 and the API on :8000 without CORS dramas.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
