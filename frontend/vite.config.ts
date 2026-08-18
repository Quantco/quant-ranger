import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig(({ command }) => ({
  base: "./",
  build: {
    emptyOutDir: true,
    outDir: "../quant_ranger/_frontend",
  },
  plugins: [react()],
  // Local JSON fixtures are useful during development but must never enter the
  // distributed Python package.
  publicDir: command === "serve" ? "public" : false,
}));
