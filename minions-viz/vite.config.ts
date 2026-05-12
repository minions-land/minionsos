import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  root: "src/web",
  base: "/",
  resolve: {
    alias: { "@shared": resolve(__dirname, "src/shared") },
  },
  build: {
    outDir: "../../dist/web",
    emptyOutDir: true,
    target: "es2022",
    sourcemap: false,
  },
  server: {
    port: 5174,
    proxy: {
      "/api": "http://localhost:7891",
      "/ws": { target: "ws://localhost:7891", ws: true },
    },
  },
});
