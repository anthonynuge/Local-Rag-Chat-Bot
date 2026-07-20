# API Contract

Frontend and backend depend only on this file; either side can change freely
as long as it honors these shapes. Base URL in dev:
`http://localhost:8000`. Frontend runs on `http://localhost:5173` (CORS allows
it).

## `GET /api/health`

Startup/liveness probe. Fails fast if the system can't serve grounded answers
(Ollama unreachable, model missing, or index not loaded) so failures surface
before a chat, not mid-stream.

**200 OK** — budget numbers below are **illustrative**; authoritative values live
in [architecture.md#config](architecture.md#config).

```json
{
  "status": "ok",
  "ollama": { "reachable": true, "host": "http://localhost:11434" },
  "models": {
    "chat": "llama3.2:3b",
    "embed": "nomic-embed-text",
    "present": true
  },
  "index": { "loaded": true, "chunks": 42, "sources": 6 },
  "budget": {
    "num_ctx": 6144,
    "answer_reserve": 1024,
    "safety_frac": 0.1,
    "input_budget": 4608,
    "context_budget": 3000
  }
}
```

**503 Service Unavailable** — same shape, `status: "unhealthy"`, with the failing
field set (`reachable: false`, `present: false`, or `loaded: false`) and a
`reason` string.

## `POST /api/chat`

Ask a question. Server assembles the prompt within the 6K budget, retrieves
context, and **streams** the answer. The server is stateless: the client sends
the full conversation history each turn.

**Request**

```json
{
  "message": "What is the PTO policy?",
  "history": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

`history` is optional (omit or `[]` for the first turn). Oldest turns may be
dropped server-side to fit the budget — see [architecture.md](architecture.md).

**400 Bad Request** — validation caught **before** streaming starts: empty
`message`, or a question so large that system prompt + question alone exceed
`input_budget` (rejected, never silently truncated). Plain JSON, not SSE:

```json
{ "detail": "human-readable reason" }
```

**Response (200)** — `Content-Type: text/event-stream` (SSE). Events, in order:

| Event               | When                             | `data` payload                                                                              |
| ------------------- | -------------------------------- | ------------------------------------------------------------------------------------------- |
| _(default)_ `token` | repeated, as the model generates | `{"delta": "text piece"}`                                                                   |
| `citations`         | once, after generation           | `{"citations": [ {"id": 1, "source": "pto-policy.md", "heading": "Accrual", "text": "chunk text…"} ] }` |
| `done`              | once, last                       | `{"prompt_eval_count": 512, "eval_count": 180, "budget": { ...per-slice token counts... }}` |
| `error`             | on failure (replaces `done`)     | `{"message": "human-readable reason"}`                                                       |

**Wire format** (standard SSE):

```
event: token
data: {"delta": "Full-time"}

event: token
data: {"delta": " employees accrue"}

event: citations
data: {"citations": [{"id": 1, "source": "pto-policy.md", "heading": "Accrual", "text": "Full-time employees accrue…"}]}

event: done
data: {"prompt_eval_count": 512, "eval_count": 180, "eval_duration": 950000000, "budget": {"system": 240, "context": 2100, "history": 0, "question": 12}}
```

### Contract rules

- The assistant cites sources inline as `[1]`, `[2]`; ids map to the `citations`
  event. The frontend renders the citation list beneath the answer.
- **Grounding:** an out-of-corpus question yields an answer with a refusal and an
  **empty** `citations` array.
- `done.budget` per-slice counts always satisfy
  `system + context + history + question ≤ input_budget`.
- `done.prompt_eval_count + answer_reserve ≤ num_ctx` (6144). This is the
  empirical proof the 6K window is respected.
- On `error`, the stream ends; no `done` event follows.

### Client expectations (frontend)

- On a non-200 status, the body is JSON (`detail`), not SSE — render it, don't parse the stream.
- Read the stream incrementally; append each `token.delta` to the active bubble.
- On `citations`, render the source list.
- On `error`, show the message inline instead of hanging.
- Never assume answer wording — only structure (this keeps the sides decoupled
  and tests stable).
