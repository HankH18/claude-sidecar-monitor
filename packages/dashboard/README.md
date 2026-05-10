# Sidecar — dashboard

React 18 + Vite + TS + Tailwind PWA for `claude-sidecar-monitor`. Loads from `/` on the collector daemon at `http://127.0.0.1:8765`.

## Local development

```bash
cd packages/dashboard
bun install
bun run dev          # http://localhost:5173 (proxies /api, /stream, /healthz to :8765)
bun run test         # vitest
bun run typecheck    # tsc -b --noEmit
bun run lint         # biome check src
bun run build        # static bundle to dist/
bun run preview      # serve the built bundle
```

## Layout

- `src/api/` — fetch wrappers, SSE client, response types (mirror Pydantic).
- `src/components/` — shared bits (state pill, token badge, tree node).
- `src/pages/` — Overview (`/`), ProjectDetail (`/projects/:encoded`), SessionDetail (`/sessions/:id`), Tokens (`/tokens`), Settings (`/settings`).
- `public/icons/` — PWA icons (192/512/maskable + apple-touch-icon-180).

## PWA

`vite-plugin-pwa` generates `manifest.webmanifest` and a service worker. `apple-mobile-web-app-capable` meta in `index.html` handles iOS standalone mode. Icons live under `public/icons/`.
