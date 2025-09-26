# Ocean Chat Backend (FastAPI + RAG + Postgres pgvector)

This backend provides a Retrieval-Augmented Generation (RAG) API compatible with the Next.js frontend. It integrates with:
- OpenAI GPT-3.5/4 for language generation
- Postgres with pgvector for similarity search
- Streaming NDJSON responses with grounded references

## Quick Start

1) Install dependencies (Python 3.10+ recommended):

```bash
pip install -r requirements.txt
```

2) Set environment variables (see .env.example). Weather answers are mocked/demo by default (no external API call). For reference to live API setup, see below:

```bash
# Example (do NOT commit secrets):
export OPENAI_API_KEY="sk-..."
export DATABASE_URL="postgresql+psycopg://user:pass@host:5432/dbname"
export OPENAI_EMBEDDING_MODEL="text-embedding-3-small"
export OPENAI_CHAT_MODEL="gpt-4o-mini"
export HOST="0.0.0.0"
export PORT="8080"
# Weather (optional; only needed if you later switch to live API calls)
export OPENWEATHERMAP_API_KEY="owm-..."
```

Security note:
- Never commit your real OPENAI_API_KEY to version control.
- In production, set OPENAI_API_KEY as a container/service environment variable (e.g., in your orchestrator or hosting platform).
- For local development, you can create a .env file based on .env.example and set OPENAI_API_KEY there.

3) Ensure your Postgres has pgvector extension installed. Create needed tables:

```bash
python -m app.db.migrations
```

4) Run the server:

```bash
uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8080}"
```

The API will be available at:
- http://localhost:8080
- OpenAPI docs: http://localhost:8080/docs

## Endpoints

- POST /api/ask
  - Request:
    ```json
    {
      "prompt": "Your question",
      "history": [{ "role": "user", "content": "previous" }, { "role": "assistant", "content": "answer" }]
    }
    ```
  - Response: Streaming NDJSON lines, examples:
    ```json
    { "type": "start", "messageId": "optional-id" }
    { "type": "token", "value": "partial text " }
    { "type": "refs", "value": [ { "title":"Doc", "url":"https://...", "snippet":"..." } ] }
    { "type": "done" }
    ```
  - Error example:
    ```json
    { "type": "error", "error": "message" }
    ```

- POST /api/ingest
  - Ingest placeholder; accepts URLs or text blobs to index.
  - Example body:
    ```json
    {
      "documents": [
        { "title": "Doc A", "url": "https://example.com/a", "text": "content..." },
        { "title": "Doc B", "url": null, "text": "another content..." }
      ]
    }
    ```

- POST /api/reindex
  - Recomputes embeddings for all stored docs (placeholder).

## Environment Variables

See `.env.example` for a complete list. Key variables:

- OPENAI_API_KEY: OpenAI API Key (required)
- OPENAI_CHAT_MODEL: Chat model (default: gpt-4o-mini; alternatives: gpt-4o, gpt-4.1, gpt-3.5-turbo, etc.)
- OPENAI_EMBEDDING_MODEL: Embedding model (default: text-embedding-3-small)
- DATABASE_URL: SQLAlchemy URL to Postgres with pgvector extension (required)
  - Example: `postgresql+psycopg://user:pass@host:5432/dbname`
- RAG_TOP_K: Number of nearest docs to retrieve (default: 4)
- HOST, PORT: Server bind config (defaults 0.0.0.0:8080)

Note: The orchestrator will set these in the runtime environment; do not commit secrets.

## Database Schema (pgvector)

We use a simple table to hold documents and their embeddings:

- documents
  - id (uuid)
  - title (text)
  - url (text, nullable)
  - text (text)
  - embedding (vector) — pgvector column
  - created_at (timestamp)

Ensure pgvector is installed in your database:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

The migration script will handle table creation with vector dimension matching the embedding model.

## Wiring the Frontend

The Next.js frontend includes a stub at `chatbot_frontend/src/app/api/ask/route.ts`. To use this real backend, set:

- NEXT_PUBLIC_BACKEND_URL=https://your-backend-host:8080

Then update the stub to forward requests to the backend or configure a proxy rewrite. Example forwarding (in the route.ts):

```ts
const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL;
const resp = await fetch(`${BACKEND}/api/ask`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(payload),
});
return new Response(resp.body, { headers: { "content-type": "application/x-ndjson" }});
```

Alternatively, use Next rewrites in `next.config.ts`:
```ts
async rewrites() {
  return [{ source: "/api/ask", destination: "http://localhost:8080/api/ask" }];
}
```

## Development Notes

- Embedding generation and ingestion are provided as placeholders to be adapted for your data source.
- Retrieval uses cosine similarity in pgvector with `embedding <=> query_embedding` order by distance.
- The streaming implementation yields NDJSON chunks to the client as tokens arrive from OpenAI.
- Errors are also returned as NDJSON with `{ "type": "error", "error": "..." }`.

## Security

- Do not expose your OpenAI API key to the frontend.
- Use HTTPS in production.
- Validate inputs and consider rate limiting and auth in production deployments.
