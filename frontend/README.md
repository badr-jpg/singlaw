# SingLaw frontend

React 19 + TypeScript + Vite SPA (TanStack Router, TanStack Query, shadcn/ui, Tailwind v4,
streamdown). Talks to the FastAPI backend in `../backend` through `src/lib/api.ts`
(typed client) and `src/lib/chat-stream.ts` (SSE chat).

- `npm run dev` — Vite on :5173, `/api` proxied to :8000
- `npm run build` — typecheck + production build into `dist/` (served by the backend)
- `npm test` — vitest
