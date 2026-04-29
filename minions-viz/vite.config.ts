import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

const isGHPages = process.env.GITHUB_PAGES === "true";

export default defineConfig({
  plugins: [react()],
  root: "src/web",
  base: isGHPages ? "/minions-viz/" : "/",
  resolve: {
    alias: { "@shared": resolve(__dirname, "src/shared") },
  },
  build: {
    outDir: "../../dist/web",
    emptyOutDir: true,
  },
  server: {
    port: 5174,
    proxy: {
      "/api": "http://localhost:7893",
      "/ws": { target: "ws://localhost:7893", ws: true },
    },
  },
});
