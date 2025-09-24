from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Global configuration loaded from environment variables."""

    OPENAI_API_KEY: str = Field(..., description="OpenAI API Key")
    OPENAI_CHAT_MODEL: str = Field("gpt-4o-mini", description="OpenAI chat model name")
    OPENAI_EMBEDDING_MODEL: str = Field("text-embedding-3-small", description="OpenAI embedding model name")
    DATABASE_URL: str = Field(..., description="SQLAlchemy URL for Postgres with pgvector")
    RAG_TOP_K: int = Field(4, description="Number of nearest documents to retrieve")

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache settings."""
    return Settings()  # type: ignore[arg-type]
```

Explanation: Define Pydantic schemas for requests and internal reference structure.
````write file="grounded-faq-chatbot-36176-36185/chatbot_backend/app/schemas.py"
from pydantic import BaseModel, Field
from typing import Optional, List


class ChatMessage(BaseModel):
    """Represents a single chat turn message."""
    role: str = Field(..., description="Message role: user|assistant|system")
    content: str = Field(..., description="Message content text")


class AskRequest(BaseModel):
    """Request model for /api/ask"""
    prompt: str = Field(..., description="User question")
    history: Optional[List[ChatMessage]] = Field(default=None, description="Optional chat history")


class DocumentIn(BaseModel):
    title: str = Field(..., description="Document title")
    url: Optional[str] = Field(default=None, description="Source URL if applicable")
    text: str = Field(..., description="Full text content to index")


class IngestRequest(BaseModel):
    documents: List[DocumentIn] = Field(..., description="Documents to ingest")


class Reference(BaseModel):
    title: str
    url: Optional[str]
    snippet: str
```

Explanation: Add DB session management and async engine/session helpers.
````write file="grounded-faq-chatbot-36176-36185/chatbot_backend/app/db/session.py"
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from typing import Optional

from ..settings import Settings, get_settings

_engine = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

def get_engine(settings: Settings):
    global _engine
    if _engine is None:
        # Ensure async driver
        if not settings.DATABASE_URL.startswith("postgresql+psycopg"):
            raise ValueError("DATABASE_URL must use 'postgresql+psycopg' driver for async SQLAlchemy.")
        _engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
    return _engine

def get_session_factory(settings: Settings):
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(settings), expire_on_commit=False)
    return _session_factory

async def ensure_db_ready():
    """Create required extension and tables if not present."""
    settings = get_settings()
    engine = get_engine(settings)
    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Create documents table if not exists (dim based on embedding model; 1536 suitable for text-embedding-3-*)
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS documents (
                  id UUID PRIMARY KEY,
                  title TEXT NOT NULL,
                  url TEXT NULL,
                  text TEXT NOT NULL,
                  embedding VECTOR(1536) NOT NULL,
                  created_at TIMESTAMP DEFAULT NOW()
                )
                """
            )
        )
        # Index for ANN search
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_documents_embedding
                ON documents
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
                """
            )
        )
```

Explanation: Add migration entrypoint to initialize DB schema.
````write file="grounded-faq-chatbot-36176-36185/chatbot_backend/app/db/migrations.py"
import asyncio
from .session import ensure_db_ready

def main():
    asyncio.run(ensure_db_ready())

if __name__ == "__main__":
    main()
```

Explanation: Implement embeddings, retrieval, and OpenAI chat streaming logic with placeholders where needed.
````write file="grounded-faq-chatbot-36176-36185/chatbot_backend/app/rag.py"
from typing import List, Tuple, Optional, AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI

from .schemas import ChatMessage, Reference
from .settings import Settings
from .db.session import get_session_factory

# Embedding vector dimension chosen in table: 1536 to match text-embedding-3-*
EMBED_DIM = 1536

async def embed_texts(texts: List[str], settings: Settings) -> List[List[float]]:
    """
    Generates embeddings for a list of texts using OpenAI embeddings API.
    """
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    # Batch embedding
    resp = await client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=texts,
    )
    vecs = [d.embedding for d in resp.data]
    return vecs


async def retrieve_context_with_refs(query: str, top_k: int, settings: Settings) -> Tuple[str, List[Reference]]:
    """
    Performs vector search over 'documents' and returns concatenated context + refs list.
    """
    # Compute query embedding
    q_emb = (await embed_texts([query], settings))[0]

    session_factory = get_session_factory(settings)
    refs: List[Reference] = []
    chunks: List[str] = []

    async with session_factory() as session:  # type: AsyncSession
        # Perform similarity search using cosine distance operator <=> with pgvector
        sql = text(
            """
            SELECT id, title, url, text, (embedding <=> :q) AS distance
            FROM documents
            ORDER BY embedding <=> :q
            LIMIT :k
            """
        )
        # Passing vector as Python list is supported by pgvector psycopg adapter
        rows = (await session.execute(sql, {"q": q_emb, "k": int(top_k)})).all()

        for row in rows:
            title = row.title
            url = row.url
            text_blob = row.text
            # Build reference snippet (simple truncation)
            snippet = text_blob[:300] + ("..." if len(text_blob) > 300 else "")
            refs.append(Reference(title=title, url=url, snippet=snippet))
            # Build context blocks
            chunks.append(f"[{title}] {snippet}")

    context_text = "\n\n".join(chunks) if chunks else ""
    return context_text, refs


class OpenAIChatStreamer:
    """
    Streams chat completion tokens from OpenAI. Injects retrieved context as system content.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def stream_chat(
        self,
        prompt: str,
        history: List[ChatMessage],
        context: str,
    ) -> AsyncGenerator[str, None]:
        """
        Yields token strings as they arrive.
        """
        # Compose messages with context grounding
        messages = []
        if context:
            messages.append({"role": "system", "content": f"You are a helpful assistant. Use the provided context to answer.\nContext:\n{context}\nIf the answer is not in the context, say you do not know."})
        # Append history
        for m in history:
            # guard roles
            role = m.role if m.role in ("user", "assistant", "system") else "user"
            messages.append({"role": role, "content": m.content})
        # Current user prompt
        messages.append({"role": "user", "content": prompt})

        stream = await self.client.chat.completions.create(
            model=self.settings.OPENAI_CHAT_MODEL,
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
```

Explanation: Add ingestion logic with placeholder handling for documents and embedding generation.
````write file="grounded-faq-chatbot-36176-36185/chatbot_backend/app/ingest.py"
import uuid
from typing import List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import DocumentIn
from .settings import Settings
from .db.session import get_session_factory
from .rag import embed_texts

async def ingest_documents(documents: List[DocumentIn], settings: Settings) -> int:
    """
    Stores documents and generates embeddings for retrieval.
    Placeholder: expects text in request and uses OpenAI to embed.
    """
    if not documents:
        return 0

    texts = [d.text for d in documents]
    embeddings = await embed_texts(texts, settings)
    session_factory = get_session_factory(settings)

    async with session_factory() as session:  # type: AsyncSession
        async with session.begin():
            for doc, vec in zip(documents, embeddings):
                await session.execute(
                    text(
                        """
                        INSERT INTO documents (id, title, url, text, embedding)
                        VALUES (:id, :title, :url, :text, :embedding)
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "title": doc.title,
                        "url": doc.url,
                        "text": doc.text,
                        "embedding": vec,
                    },
                )
    return len(documents)


async def reindex_all(settings: Settings) -> int:
    """
    Recompute embeddings for all documents. This is a placeholder simplistic approach:
    - Fetch all docs
    - Re-embed text
    - Update vector
    """
    session_factory = get_session_factory(settings)
    async with session_factory() as session:  # type: AsyncSession
        rows = (await session.execute(text("SELECT id, text FROM documents"))).all()
        if not rows:
            return 0
        ids = [r.id for r in rows]
        texts = [r.text for r in rows]

        embeddings = await embed_texts(texts, settings)

        async with session.begin():
            for doc_id, vec in zip(ids, embeddings):
                await session.execute(
                    text(
                        """
                        UPDATE documents
                        SET embedding = :embedding
                        WHERE id = :id
                        """
                    ),
                    {"embedding": vec, "id": doc_id},
                )
        return len(ids)
```

Explanation: Add package initializer to ensure package importability.
````write file="grounded-faq-chatbot-36176-36185/chatbot_backend/app/__init__.py"
# Package initializer for app
