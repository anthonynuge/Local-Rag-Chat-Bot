import { useState } from "react"

import { streamChat, type Citation, type Turn } from "@/api"
import Composer from "@/components/Composer"
import HealthDot from "@/components/HealthDot"
import MessageList from "@/components/MessageList"

export interface Message {
  role: "user" | "assistant"
  content: string
  citations?: Citation[]
  streaming?: boolean
}

function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function send(text: string) {
    setError(null)
    // The API is stateless: send all prior turns as history each time.
    const history: Turn[] = messages.map(({ role, content }) => ({ role, content }))

    setMessages((previous) => [
      ...previous,
      { role: "user", content: text },
      { role: "assistant", content: "", streaming: true },
    ])
    setStreaming(true)

    function finish() {
      setMessages((previous) => updateLast(previous, (m) => ({ ...m, streaming: false })))
      setStreaming(false)
    }

    await streamChat(text, history, {
      onToken: (delta) =>
        setMessages((previous) =>
          updateLast(previous, (m) => ({ ...m, content: m.content + delta })),
        ),
      onCitations: (citations) =>
        setMessages((previous) => updateLast(previous, (m) => ({ ...m, citations }))),
      onDone: finish,
      onError: (message) => {
        setError(message)
        finish()
      },
    })
  }

  const empty = messages.length === 0

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <header className="flex items-center justify-between border-b border-border px-6 py-3">
        <h1 className="text-lg font-semibold">Local RAG Chat</h1>
        <HealthDot />
      </header>

      {empty ? (
        // First visit: greeting with the composer right under it, centered.
        <main className="flex flex-1 animate-message-in flex-col items-center justify-center gap-6 px-4 pb-24">
          <div className="text-center">
            <h2 className="text-2xl font-semibold">Ask about the company wiki</h2>
            <p className="mt-2 text-muted-foreground">Answers cite their sources.</p>
          </div>
          <div className="w-full max-w-3xl">
            <Composer disabled={streaming} onSend={send} />
          </div>
        </main>
      ) : (
        // Chat underway: messages fill the screen, composer docks at the bottom.
        <>
          <MessageList messages={messages} />

          {error !== null && (
            <div className="mx-auto w-full max-w-3xl px-4 pb-2">
              <p className="rounded-lg bg-destructive/10 px-4 py-2 text-[13px] text-destructive">
                {error}
              </p>
            </div>
          )}

          <footer className="px-4 pb-6 pt-2">
            <div className="mx-auto max-w-3xl">
              <Composer disabled={streaming} onSend={send} />
            </div>
          </footer>
        </>
      )}
    </div>
  )
}

/** Apply an update to the last message (the streaming assistant turn). */
function updateLast(list: Message[], update: (message: Message) => Message): Message[] {
  return list.map((message, index) => (index === list.length - 1 ? update(message) : message))
}

export default App
