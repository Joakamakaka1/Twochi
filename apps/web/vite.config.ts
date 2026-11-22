import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  // TWOCHI_DEV_API_URL: where the local API listens, from the shell or .env.local.
  const env = loadEnv(mode, ".", "TWOCHI_");
  return {
    plugins: [react()],
    server: {
      // In production CloudFront serves /api from the page's origin; here Vite does.
      proxy: { "/api": env.TWOCHI_DEV_API_URL ?? "http://127.0.0.1:8000" },
    },
    test: {
      include: ["src/**/*.test.{ts,tsx}"],
    },
  };
});
