# Ocean Chat Frontend (Next.js)

Modern, minimalist chat UI with Ocean Professional theme. Centered chat panel, sidebar for history, and streaming responses with references.

## Run locally

```bash
npm install
npm run dev
# open http://localhost:3000
```

## UI Overview

- Ocean Professional theme using blue and amber accents.
- Centered chat panel with message bubbles and a bottom composer.
- Left sidebar: basic static history placeholders (can be wired later).
- Answers support streaming tokens and grounded references (citations).
- Keyboard: Enter to send, Shift+Enter for newline.

## Backend Interface

The UI integrates with a backend route at:

- POST /api/ask

This repository includes a stubbed Next.js API route at `src/app/api/ask/route.ts` that streams NDJSON to unblock the chat UI locally. Replace the stub with a call to your real backend when available.

To wire a real backend:
- Set an environment variable (request from orchestrator): `NEXT_PUBLIC_BACKEND_URL=https://your-backend-host`
- In `src/app/api/ask/route.ts`, forward the request: 
  `await fetch(\`\${process.env.NEXT_PUBLIC_BACKEND_URL}/api/ask\`, { method: "POST", headers, body })` and stream the response body back to the client.
- Alternatively, configure Next.js rewrites in `next.config.ts` to proxy `/api/ask` to your backend service.

Expected request payload:

```json
{
  "prompt": "Your question",
  "history": [{ "role": "user", "content": "previous" }, { "role": "assistant", "content": "answer" }]
}
```

Expected streaming response over the HTTP body as NDJSON lines (one JSON per line). Supported chunk shapes:

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

- History is currently in-memory; a small localStorage helper is included at `src/lib/history.ts` for future use.
- This app is exportable (next.config.ts has `output: "export"`). Ensure backend is available when deployed behind the same origin.
