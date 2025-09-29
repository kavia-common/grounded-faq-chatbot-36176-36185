# Ocean Chat Frontend (Next.js)

Modern, minimalist chat UI with Ocean Professional theme. Centered chat panel, sidebar for history, and streaming responses with references.

## Run locally

```bash
cp .env.example .env                 # set NEXT_PUBLIC_BACKEND_URL if using a real backend
# .env (do NOT commit real values)
# NEXT_PUBLIC_BACKEND_URL=https://localhost:8000
npm install
npm run dev
# open http://localhost:3000
```

How proxying works:
- If `NEXT_PUBLIC_BACKEND_URL` is set, there are two layers that can route your request to the real backend:
  1) A Next.js rewrite defined in `next.config.ts` that proxies `/api/ask` to `${NEXT_PUBLIC_BACKEND_URL}/api/ask` (avoids CORS).
  2) The API route `src/app/api/ask/route.ts` will also forward the request server-side when `NEXT_PUBLIC_BACKEND_URL` is set, streaming the backend response to the browser.
- If the backend is unreachable, the API route returns an NDJSON error line such as:
  `{ "type": "error", "error": "Backend unavailable (...)" }`, which the UI displays to the user.
- If `NEXT_PUBLIC_BACKEND_URL` is not set, the API route falls back to a local stub that streams demo tokens and references.

## UI Overview

- Ocean Professional theme using blue and amber accents.
- Centered chat panel with message bubbles and a bottom composer.
- Left sidebar: basic static history placeholders (can be wired later).
- Answers support streaming tokens and grounded references (citations).
- Keyboard: Enter to send, Shift+Enter for newline.

## Backend Interface

The UI integrates with a backend route at:

- POST /api/ask

The repo ships with a stubbed Next.js API route at `src/app/api/ask/route.ts` that streams NDJSON so you can test the chat UI without a backend.

To connect a real backend:
- Set `NEXT_PUBLIC_BACKEND_URL=https://your-backend-host:8080` (request the value from the orchestrator; do not commit real envs).
- Option A (recommended): Next.js rewrite proxy is auto-configured in `next.config.ts` when `NEXT_PUBLIC_BACKEND_URL` is present to route `/api/ask` to your backend.
- Option B: The API route itself detects `NEXT_PUBLIC_BACKEND_URL` and will forward to `${NEXT_PUBLIC_BACKEND_URL}/api/ask` and stream the response back.
- Ensure your backend returns streaming NDJSON as described below.

Expected request payload:

```json
{
  "prompt": "Your question",
  "history": [{ "role": "user", "content": "previous" }, { "role": "assistant", "content": "answer" }]
}
```

Expected streaming response (NDJSON lines, one JSON per line):

```json
{ "type": "start", "messageId": "optional" }
{ "type": "token", "value": "partial text" }
{ "type": "refs", "value": [ { "title":"Doc", "url":"https://...", "snippet":"..." } ] }
{ "type": "done" }
```

Errors may be returned as:

```json
{ "type": "error", "error": "message" }
```

The frontend accumulates `token` chunks into the assistant message and shows `refs` as citations.

## Theming

- Colors are defined in `src/app/globals.css` with CSS variables.
- Tailwind is available for utility classes (Next 15 + Tailwind v4).
- Smooth gradients, subtle shadows, and rounded corners for depth.

## Notes

- History is currently in-memory.
- This app is exportable (next.config.ts has `output: "export"`). Ensure backend is available when deployed behind the same origin or via rewrites.
- Env vars:
  - NEXT_PUBLIC_BACKEND_URL: URL to your backend (for proxy/forward).
  - NEXT_PUBLIC_OPENAI_API_KEY: Placeholder; do not expose real keys client-side. All model calls should happen on the backend.
