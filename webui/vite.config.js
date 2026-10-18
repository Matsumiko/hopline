import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/status": "http://127.0.0.1:18772",
      "/nodes": "http://127.0.0.1:18772",
      "/sync": "http://127.0.0.1:18772",
      "/subscriptions": "http://127.0.0.1:18772",
      "/service": "http://127.0.0.1:18772",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
