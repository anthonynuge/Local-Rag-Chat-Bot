import { useEffect, useRef } from "react"

import type { Message } from "@/App"
import MessageBubble from "@/components/MessageBubble"

function MessageList({ messages }: { messages: Message[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Keep the newest message in view while tokens stream in.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // The empty state lives in App (centered greeting + composer) — this
  // component only renders once messages exist.
  return (
    <main className="flex-1 overflow-y-auto">
      <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6">
        {messages.map((message, index) => (
          <MessageBubble key={index} message={message} />
        ))}
        <div ref={bottomRef} />
      </div>
    </main>
  )
}

export default MessageList
