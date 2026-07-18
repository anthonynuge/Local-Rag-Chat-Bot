import { useEffect, useState } from "react"

import type { Message } from "@/App"
import CitationList from "@/components/CitationList"

/** User: secondary bubble, right-aligned. Assistant: bare text on the canvas. */
function MessageBubble({ message }: { message: Message }) {
  if (message.role === "user") {
    return (
      <div className="flex animate-message-in justify-end">
        <div className="max-w-[75%] rounded-2xl bg-secondary px-4 py-3 text-[15px] whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    )
  }

  return <AssistantMessage message={message} />
}

function AssistantMessage({ message }: { message: Message }) {
  const displayed = useSmoothText(message.content, message.streaming === true)
  const waitingForFirstToken = message.streaming && displayed === ""
  const revealing = message.streaming || displayed.length < message.content.length

  return (
    <div className="animate-message-in">
      {waitingForFirstToken ? (
        <ThinkingDots />
      ) : (
        <p className="whitespace-pre-wrap text-[15px] leading-7">
          {displayed}
          {revealing && (
            <span className="-mb-0.5 ml-0.5 inline-block h-4 w-0.5 animate-caret bg-foreground" />
          )}
        </p>
      )}
      {message.citations !== undefined && !revealing && (
        <CitationList citations={message.citations} />
      )}
    </div>
  )
}

/** Reveal streamed text at a steady pace instead of network bursts.
 *
 * The stream fills `target` as fast as it arrives; this reveals it a few
 * characters per tick, stepping faster the further behind it falls so the
 * display never lags the model by much. Snaps to the end when streaming stops.
 */
function useSmoothText(target: string, streaming: boolean): string {
  const [visibleCount, setVisibleCount] = useState(0)

  useEffect(() => {
    if (!streaming) {
      setVisibleCount(target.length)
      return
    }

    const timer = setInterval(() => {
      setVisibleCount((current) => {
        const behind = target.length - current
        if (behind <= 0) {
          return current
        }
        // ~40 chars/s cruising; accelerate when a burst lands.
        const step = behind > 120 ? 6 : behind > 40 ? 3 : 1
        return current + step
      })
    }, 24)

    return () => clearInterval(timer)
  }, [target, streaming])

  return target.slice(0, visibleCount)
}

function ThinkingDots() {
  return (
    <div className="flex gap-1.5 py-2" aria-label="Waiting for answer">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-2 w-2 animate-thinking rounded-full bg-primary"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  )
}

export default MessageBubble
