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
      // Self-destroy: the SW unregisters on next page load. We disabled
      // PWA caching because the SW's NavigationRoute serves the precached
      // index.html for every nav request, bypassing the server-side
      // csm-token substitution. Until the SW grows a NetworkFirst HTML
      // strategy AND we ship a non-templated dev shell, keep it off.
      // Setting `selfDestroying: true` also handles users with a stale SW
      // from earlier V2 builds — they'll be cleaned up automatically.
      selfDestroying: true,
      includeAssets: ["favicon.svg", "apple-touch-icon-180.png"],
      manifest: {
        name: "Sidecar",
        short_name: "Sidecar",
        description: "Claude Code agent monitor",
        theme_color: "#e8dfc8",
        background_color: "#e8dfc8",
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
        // SSE responses must not be cached. /api/openapi.json and /api/docs
        // are auto-mounted by FastAPI — keep them out of the precache too.
        navigateFallbackDenylist: [
          /^\/stream/,
          /^\/api\//,
          /^\/hook\//,
          /^\/healthz/,
        ],
        // After a deploy with new hashed JS/CSS, the old precached HTML
        // shell references stale asset hashes; without skipWaiting+clientsClaim
        // an iOS standalone PWA can serve the shell, then 404 on the new
        // assets until the user fully closes and re-opens the app. Force
        // the new service worker active immediately and take control of
        // open clients so the next navigation fetches the fresh shell.
        skipWaiting: true,
        clientsClaim: true,
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
