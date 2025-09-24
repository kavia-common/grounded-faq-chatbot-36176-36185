/* Using the runtime-standard Request type for App Route handlers (Next.js 15) */

/**
 * PUBLIC_INTERFACE
 * POST /api/ask
 * A stubbed streaming NDJSON chat endpoint used by the frontend chat UI.
 *
 * Request body:
 * {
 *   "prompt": string,
 *   "history": [{ "role": "user" | "assistant" | "system", "content": string }]
 * }
 *
 * Response:
 * - Streams NDJSON lines with shapes:
 *   { "type": "start", "messageId": "optional-id" }
 *   { "type": "token", "value": "partial text" }
 *   { "type": "refs", "value": [ { "title": "Doc", "url": "https://...", "snippet": "..." } ] }
 *   { "type": "done" }
 *   On error: { "type": "error", "error": "message" }
 *
 * Notes:
 * - This is a frontend-only stub to unblock UI development. Replace the internal logic
 *   with a call to the real backend (e.g., fetch(`${BACKEND_URL}/api/ask`, { ... }))
 *   and pipe its streamed response back to the client.
 */
export async function POST(req: Request): Promise<Response> {
  try {
    // Validate content type
    const ctype = req.headers.get("content-type") || "";
    if (!ctype.includes("application/json")) {
      return new Response(JSON.stringify({ type: "error", error: "Unsupported Media Type" }) + "\n", {
        status: 415,
        headers: {
          "content-type": "application/x-ndjson; charset=utf-8",
          "cache-control": "no-store",
        },
      });
    }

    const body = await req.json().catch(() => null) as
      | { prompt?: string; history?: Array<{ role: "user" | "assistant" | "system"; content: string }> }
      | null;

    if (!body || typeof body.prompt !== "string" || body.prompt.trim().length === 0) {
      return new Response(JSON.stringify({ type: "error", error: "Invalid request: missing prompt" }) + "\n", {
        status: 400,
        headers: {
          "content-type": "application/x-ndjson; charset=utf-8",
          "cache-control": "no-store",
        },
      });
    }

    const prompt = body.prompt.trim();

    // Example: Integrate with a real backend
    // const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL; // do NOT hardcode; use .env
    // if (!BACKEND_URL) { /* return error or fallback */ }
    // const backendResp = await fetch(`${BACKEND_URL}/api/ask`, { method: "POST", headers: {...}, body: JSON.stringify(body) });
    // return new Response(backendResp.body, {
    //   status: backendResp.status,
    //   headers: { "content-type": "application/x-ndjson; charset=utf-8" },
    // });

    // Stubbed streaming response to emulate token-by-token generation
    const stream = new ReadableStream({
      start(controller) {
        // Helper to enqueue a JSON line
        const send = (obj: Record<string, unknown>) => {
          const line = JSON.stringify(obj) + "\n";
          controller.enqueue(new TextEncoder().encode(line));
        };

        // Simulate async token streaming
        const tokens = [
          "Here", " is", " a", " grounded", " answer", " about", " your", " question", " \"",
          prompt.slice(0, 64), "\".", " ",
          "This", " is", " a", " demo", " response", " generated", " by", " the", " stubbed", " endpoint."
        ];

        // Start event
        send({ type: "start", messageId: `msg_${Date.now()}` });

        let i = 0;
        const interval = setInterval(() => {
          if (i < tokens.length) {
            send({ type: "token", value: tokens[i++] });
          } else {
            clearInterval(interval);

            // Send references once at the end
            send({
              type: "refs",
              value: [
                {
                  id: "ref1",
                  title: "Project README",
                  url: "https://example.com/docs/readme",
                  snippet: "Learn how the grounded FAQ chatbot works and how to query it.",
                  score: 0.92,
                },
                {
                  id: "ref2",
                  title: "FAQ: Getting Started",
                  url: "https://example.com/docs/faq#getting-started",
                  snippet: "Common steps to set up and ask questions effectively.",
                  score: 0.88,
                },
              ],
            });

            // Done event
            send({ type: "done" });
            controller.close();
          }
        }, 60);
      },
      cancel() {
        // If client cancels, nothing else to do in stub
      },
    });

    return new Response(stream, {
      status: 200,
      headers: {
        "content-type": "application/x-ndjson; charset=utf-8",
        "cache-control": "no-store",
      },
    });
  } catch (err) {
    const message =
      typeof err === "object" && err !== null && "message" in err
        ? String((err as { message?: string }).message)
        : "Internal server error";

    // Return error as NDJSON line; still a 200 body to align with streaming expectations,
    // but you could also choose an error status. The frontend handles { type: "error" } lines.
    return new Response(JSON.stringify({ type: "error", error: message }) + "\n", {
      status: 200,
      headers: {
        "content-type": "application/x-ndjson; charset=utf-8",
        "cache-control": "no-store",
      },
    });
  }
}
