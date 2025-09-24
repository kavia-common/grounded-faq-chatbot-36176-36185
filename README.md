# grounded-faq-chatbot-36176-36185

This workspace contains:
- chatbot_frontend: Next.js chat UI (streams NDJSON) at `/api/ask` stub.
- chatbot_backend: FastAPI RAG backend with OpenAI + Postgres/pgvector.

## Running Locally

Frontend:
```bash
cd chatbot_frontend
npm install
npm run dev
# open http://localhost:3000
```

Backend:
```bash
cd chatbot_backend
pip install -r requirements.txt
python -m app.db.migrations  # creates pgvector extension and documents table
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Required environment variables (set in your environment; do not commit secrets):
- OPENAI_API_KEY
- DATABASE_URL (e.g., postgresql+psycopg://user:pass@host:5432/db)
- OPENAI_CHAT_MODEL (default gpt-4o-mini)
- OPENAI_EMBEDDING_MODEL (default text-embedding-3-small)
- RAG_TOP_K (default 4)

See chatbot_backend/.env.example for details.

## Wiring Frontend -> Backend

Set:
```bash
export NEXT_PUBLIC_BACKEND_URL="http://localhost:8080"
```

In `chatbot_frontend/src/app/api/ask/route.ts`, forward the request to the backend and stream the response body back to the client, or configure a rewrite in `next.config.ts` to proxy `/api/ask` to the backend.

The backend streams NDJSON with chunk types: start, token, refs, done (or error).