import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "");
  const target = env.VITE_API_BASE || "http://localhost:8000";
  return {
    plugins: [react()],
    build: { rollupOptions: { output: { manualChunks: { cytoscape: ["cytoscape"], react: ["react", "react-dom"] } } } },
    server: { port: 5173, proxy: { "/api": target, "/health": target } },
    preview: { port: 4173, proxy: { "/api": target, "/health": target } },
  };
});
