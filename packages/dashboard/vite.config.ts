/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "apple-touch-icon-180.png"],
      manifest: {
        name: "Sidecar",
        short_name: "Sidecar",
        description: "Claude Code agent monitor",
        theme_color: "#0b0e14",
        background_color: "#0b0e14",
        display: "standalone",
        start_url: "/",
        scope: "/",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/icons/icon-512-maskable.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        // SSE responses must not be cached
        navigateFallbackDenylist: [/^\/stream/, /^\/api\//, /^\/hook\//, /^\/healthz/],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/stream": {
        target: "http://127.0.0.1:8765",
        changeOrigin: false,
        ws: false,
      },
      "/healthz": "http://127.0.0.1:8765",
      "/hook": "http://127.0.0.1:8765",
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
});
