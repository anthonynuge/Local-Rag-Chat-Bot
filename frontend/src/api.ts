/** SSE client for the backend, per docs/api-contract.md.
 *
 * POST /api/chat streams frames: token* -> citations -> done (or error).
 * EventSource can't POST, so we read the stream off fetch() by hand.
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000"

export interface Turn {
  role: "user" | "assistant"
  content: string
}

export interface Citation {
  id: number
  source: string
  heading: string
}

export interface BudgetReport {
  system: number
  context: number
  history: number
  question: number
  input_budget: number
}

export interface DoneData {
  prompt_eval_count: number
  eval_count: number
  budget: BudgetReport
}

export interface Health {
  status: "ok" | "unhealthy"
  reason?: string
}

export interface ChatHandlers {
  onToken(delta: string): void
  onCitations(citations: Citation[]): void
  onDone(data: DoneData): void
  onError(message: string): void
}

export async function fetchHealth(): Promise<Health> {
  try {
    const response = await fetch(`${API_BASE}/api/health`)
    return (await response.json()) as Health // 503 bodies carry the same shape
  } catch {
    return { status: "unhealthy", reason: "backend unreachable" }
  }
}

export async function streamChat(
  message: string,
  history: Turn[],
  handlers: ChatHandlers,
): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
    })
  } catch {
    handlers.onError("Backend unreachable — is the server running?")
    return
  }

  // 400s (empty/oversized question) are plain JSON, not a stream.
  if (!response.ok || response.body === null) {
    const body = await response.json().catch(() => null)
    handlers.onError(body?.detail ?? `Request failed (${response.status})`)
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    buffer += decoder.decode(value, { stream: true })

    // Frames are separated by a blank line; the buffer may hold partial frames.
    let separator = buffer.indexOf("\n\n")
    while (separator !== -1) {
      const frame = buffer.slice(0, separator)
      buffer = buffer.slice(separator + 2)
      dispatchFrame(frame, handlers)
      separator = buffer.indexOf("\n\n")
    }
  }
}

function dispatchFrame(frame: string, handlers: ChatHandlers): void {
  const newline = frame.indexOf("\n")
  const eventLine = frame.slice(0, newline)
  const dataLine = frame.slice(newline + 1)
  if (!eventLine.startsWith("event: ") || !dataLine.startsWith("data: ")) {
    return
  }

  const event = eventLine.slice("event: ".length)
  const data = JSON.parse(dataLine.slice("data: ".length))

  switch (event) {
    case "token":
      handlers.onToken((data as { delta: string }).delta)
      break
    case "citations":
      handlers.onCitations((data as { citations: Citation[] }).citations)
      break
    case "done":
      handlers.onDone(data as DoneData)
      break
    case "error":
      handlers.onError((data as { message: string }).message)
      break
  }
}
