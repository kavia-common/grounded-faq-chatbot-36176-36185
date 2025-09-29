"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type Role = "user" | "assistant" | "system";

export type Reference = {
  id?: string;
  title?: string;
  snippet?: string;
  url?: string;
  score?: number;
};

export type ChatMessage = {
  id: string;
  role: Role;
  content: string;
  references?: Reference[];
};

type AskRequest = {
  prompt: string;
  history: { role: Role; content: string }[];
};

type AskChunk =
  | { type: "start"; messageId?: string }
  | { type: "token"; value: string }
  | { type: "refs"; value: Reference[] }
  | { type: "done" }
  | { type: "error"; error: string };

function uid(prefix = "id"): string {
  return `${prefix}_${Math.random().toString(36).slice(2)}_${Date.now()}`;
}

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [historyTitles, setHistoryTitles] = useState<{ id: string; title: string }[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  const canSend = useMemo(() => input.trim().length > 0 && !isLoading, [input, isLoading]);

  const sendPrompt = useCallback(async () => {
    const prompt = input.trim();
    if (!prompt) return;

    // Push user message
    const userMsg: ChatMessage = { id: uid("m"), role: "user", content: prompt };
    setMessages((prev) => [...prev, userMsg]);

    // Prepare assistant placeholder
    const assistantId = uid("m");
    const placeholder: ChatMessage = { id: assistantId, role: "assistant", content: "" };
    setMessages((prev) => [...prev, placeholder]);
    setStreamingId(assistantId);
    setIsLoading(true);
    setInput("");

    // Auto title for history (first user line)
    if (historyTitles.length === 0) {
      setHistoryTitles([{ id: uid("h"), title: prompt.slice(0, 48) }]);
    }

    try {
      const body: AskRequest = {
        prompt,
        history: messages.map((m) => ({ role: m.role, content: m.content })),
      };

      const resp = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!resp.ok || !resp.body) {
        throw new Error(`Request failed: ${resp.status} ${resp.statusText}`);
      }

      // Expecting NDJSON or SSE-like lines where each line is JSON
      const reader = resp.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      const flushJSONLines = (text: string) => {
        buffer += text;
        const lines = buffer.split(/\r?\n/);
        // Keep last partial line in buffer
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const chunk = JSON.parse(line) as AskChunk;
            if (chunk.type === "token" && typeof chunk.value === "string") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: (m.content || "") + chunk.value } : m
                )
              );
            } else if (chunk.type === "refs" && Array.isArray(chunk.value)) {
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantId ? { ...m, references: chunk.value } : m))
              );
            } else if (chunk.type === "error") {
              throw new Error(chunk.error || "Unknown error");
            }
          } catch {
            // Non-JSON lines are ignored
            // console.debug("non-JSON line", line);
          }
        }
      };

      // Read stream
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const text = decoder.decode(value, { stream: true });
        flushJSONLines(text);
      }

      // Flush any remainder as JSON if possible
      if (buffer.trim()) {
        try {
          const finalChunk = JSON.parse(buffer) as AskChunk;
          if (finalChunk.type === "refs" && Array.isArray(finalChunk.value)) {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, references: finalChunk.value } : m))
            );
          }
        } catch {
          // ignore
        }
      }
    } catch (err: unknown) {
      const message =
        typeof err === "object" && err !== null && "message" in err
          ? String((err as { message?: string }).message)
          : "Failed to get response";
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, content: `Error: ${message}` } : m))
      );
    } finally {
      setIsLoading(false);
      setStreamingId(null);
      textareaRef.current?.focus();
    }
  }, [input, messages, historyTitles.length]);

  const onKeyDown = useCallback(
    (evt: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Use key only; keyCode is deprecated and removed to avoid unused variable warnings
      if (evt.key === "Enter" && !evt.shiftKey) {
        evt.preventDefault();
        if (canSend) void sendPrompt();
      }
    },
    [canSend, sendPrompt]
  );

  return (
    <div className="chat-wrap">
      <section className="chat-panel">
        <div className="messages" ref={scrollRef} role="log" aria-live="polite">
          {messages.length === 0 ? (
            <div
              className="max-w-prose"
              style={{ margin: "1rem auto", textAlign: "center" }}
              aria-label="Empty state"
            >
              <h1 style={{ fontSize: "1.3rem", fontWeight: 600, marginBottom: ".35rem" }}>
                Ask grounded questions
              </h1>
              <p className="small-muted">
                Your answers stream in with citations from your knowledge base. Press <span className="kbd">Enter</span> to send, <span className="kbd">Shift</span>+<span className="kbd">Enter</span> for a new line.
              </p>
            </div>
          ) : null}
          {messages.map((m) => {
            const isAssistant = m.role === "assistant";
            return (
              <div
                key={m.id}
                className={`msg ${m.role}`}
                role="article"
                aria-busy={streamingId === m.id}
              >
                <div
                  className={`avatar ${isAssistant ? "avatar-assistant" : "avatar-user"}`}
                  aria-hidden
                >
                  {isAssistant ? "A" : "U"}
                </div>
                <div>
                  <div className="bubble">
                    <div className="prose" style={{ whiteSpace: "pre-wrap" }}>
                      {m.content || (streamingId === m.id ? "…" : "")}
                    </div>
                  </div>
                  {isAssistant && m.references && m.references.length > 0 ? (
                    <div className="references" aria-label="Answer references">
                      {m.references.map((r, idx) => (
                        <div key={r.id || idx} className="ref-card">
                          <div style={{ display: "flex", gap: ".5rem", alignItems: "center" }}>
                            <span
                              className="badge"
                              style={{ background: "rgba(245,158,11,0.08)", color: "#B45309", borderColor: "rgba(245,158,11,0.25)" }}
                            >
                              Ref {idx + 1}
                            </span>
                            <strong>{r.title || r.url || "Reference"}</strong>
                          </div>
                          {r.snippet ? (
                            <p className="small-muted" style={{ marginTop: ".35rem" }}>
                              {r.snippet}
                            </p>
                          ) : null}
                          {r.url ? (
                            <a
                              href={r.url}
                              target="_blank"
                              rel="noreferrer"
                              className="small-muted"
                              style={{ textDecoration: "underline" }}
                            >
                              Open source
                            </a>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })}
          {isLoading ? (
            <div className="msg assistant" aria-live="assertive">
              <div className="avatar avatar-assistant">A</div>
              <div>
                <div className="bubble small-muted">Thinking…</div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="footer">
          <div className="composer" role="form" aria-label="Chat composer">
            <textarea
              ref={textareaRef}
              className="textarea"
              placeholder="Ask a question…"
              value={input}
              onChange={(evt) => setInput(evt.currentTarget.value)}
              onKeyDown={onKeyDown}
            />
            <button
              className="btn primary"
              onClick={() => void sendPrompt()}
              disabled={!canSend}
              aria-disabled={!canSend}
              aria-label="Send message"
            >
              Send
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path
                  d="M5 12h11M12 5l7 7-7 7"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
